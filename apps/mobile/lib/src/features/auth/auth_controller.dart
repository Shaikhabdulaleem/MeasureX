import 'dart:convert';

import 'package:bcrypt/bcrypt.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../core/db/db_providers.dart';
import '../../core/session_store.dart';

enum AuthStatus { unknown, unauthenticated, mustChangePassword, authenticated }

/// Offline window = 12 h shift token + 12 h grace (PRD §10 rule 6).
const kOfflineWindow = Duration(hours: 24);

class AuthState {
  const AuthState({required this.status, this.user, this.accessToken, this.refreshToken});

  final AuthStatus status;
  final AuthUser? user;
  final String? accessToken;
  final String? refreshToken;

  AuthState copyWith({
    AuthStatus? status,
    AuthUser? user,
    String? accessToken,
    String? refreshToken,
  }) {
    return AuthState(
      status: status ?? this.status,
      user: user ?? this.user,
      accessToken: accessToken ?? this.accessToken,
      refreshToken: refreshToken ?? this.refreshToken,
    );
  }
}

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());
final sessionStoreProvider = Provider<SessionStore>((ref) => SessionStore());

final authControllerProvider =
    StateNotifierProvider<AuthController, AuthState>((ref) {
  return AuthController(ref);
});

class AuthController extends StateNotifier<AuthState> {
  AuthController(this._ref)
      : _api = _ref.read(apiClientProvider),
        _store = _ref.read(sessionStoreProvider),
        super(const AuthState(status: AuthStatus.unknown));

  final Ref _ref;
  final ApiClient _api;
  final SessionStore _store;

  /// Restore a session on launch without a network call (PRD §10 rule 6): if a
  /// stored session is still within its offline window, resume it; otherwise
  /// require a login. Local data is never touched here.
  Future<void> bootstrap() async {
    final stored = await _store.read();
    if (stored == null) {
      state = const AuthState(status: AuthStatus.unauthenticated);
      return;
    }
    if (DateTime.now().toUtc().isAfter(stored.offlineUntil.toUtc())) {
      // Window elapsed — online login required. Keep any unsynced local data.
      state = const AuthState(status: AuthStatus.unauthenticated);
      return;
    }
    state = AuthState(
      status: AuthStatus.authenticated,
      user: AuthUser.fromJson(jsonDecode(stored.userJson) as Map<String, dynamic>),
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
    );
  }

  /// Online login. Returns null on success, or an error code for the UI.
  Future<String?> login(String employeeId, String password) async {
    try {
      final tokens = await _api.login(employeeId.trim(), password);
      await _persist(employeeId.trim(), password, tokens);
      state = AuthState(
        status: tokens.mustChangePassword
            ? AuthStatus.mustChangePassword
            : AuthStatus.authenticated,
        user: tokens.user,
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
      );
      return null;
    } on ApiException catch (e) {
      return e.code;
    } catch (_) {
      return 'ERROR';
    }
  }

  /// Offline login for the last device user within the offline window (PRD §10
  /// rule 6). Verifies the password against the locally stored bcrypt hash.
  /// Returns null on success, or an error code.
  Future<String?> offlineLogin(String employeeId, String password) async {
    final stored = await _store.read();
    if (stored == null) return 'OFFLINE_LOGIN_UNAVAILABLE';
    if (DateTime.now().toUtc().isAfter(stored.offlineUntil.toUtc())) {
      return 'OFFLINE_WINDOW_EXPIRED';
    }
    if (stored.employeeId.toUpperCase() != employeeId.trim().toUpperCase()) {
      return 'INVALID_CREDENTIALS';
    }
    final ok = BCrypt.checkpw(password, stored.passwordHash);
    if (!ok) return 'INVALID_CREDENTIALS';
    state = AuthState(
      status: AuthStatus.authenticated,
      user: AuthUser.fromJson(jsonDecode(stored.userJson) as Map<String, dynamic>),
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
    );
    return null;
  }

  Future<String?> changePassword(String currentPassword, String newPassword) async {
    final token = state.accessToken;
    if (token == null) return 'ERROR';
    try {
      await _api.changePassword(token, currentPassword, newPassword);
      // Password change revokes sessions server-side; require a fresh login.
      await _store.clear();
      state = const AuthState(status: AuthStatus.unauthenticated);
      return null;
    } on ApiException catch (e) {
      return e.code;
    } catch (_) {
      return 'ERROR';
    }
  }

  /// Log out. [wipeLocal] must be true only when everything is synced: it clears
  /// the session material AND wipes the encrypted local database + key (PRD §10
  /// rule 7). When false (unsynced records exist), the local data and offline
  /// material are kept so they can still sync — the records stay on the device
  /// under the previous user (PRD §3 shared-phone rule).
  Future<void> logout({required bool wipeLocal}) async {
    final access = state.accessToken;
    final refresh = state.refreshToken;
    if (access != null && refresh != null) {
      await _api.logout(access, refresh);
    }
    if (wipeLocal) {
      await _store.clear();
      await _ref.read(appDatabaseProvider).wipe();
      await _ref.read(dbKeyStoreProvider).clear();
    }
    state = const AuthState(status: AuthStatus.unauthenticated);
  }

  Future<void> _persist(String employeeId, String password, TokenPair tokens) async {
    await _store.save(StoredSession(
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
      userJson: jsonEncode(tokens.user.toJson()),
      employeeId: employeeId,
      passwordHash: BCrypt.hashpw(password, BCrypt.gensalt()),
      offlineUntil: DateTime.now().toUtc().add(kOfflineWindow),
    ));
  }
}
