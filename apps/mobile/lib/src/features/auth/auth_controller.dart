import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_client.dart';
import '../../core/session_store.dart';

enum AuthStatus { unknown, unauthenticated, mustChangePassword, authenticated }

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
  return AuthController(ref.read(apiClientProvider), ref.read(sessionStoreProvider));
});

class AuthController extends StateNotifier<AuthState> {
  AuthController(this._api, this._store)
      : super(const AuthState(status: AuthStatus.unauthenticated));

  final ApiClient _api;
  final SessionStore _store;

  /// Log in. Returns null on success, or an error code for the UI to localise.
  Future<String?> login(String employeeId, String password) async {
    try {
      final tokens = await _api.login(employeeId.trim(), password);
      await _store.save(accessToken: tokens.accessToken, refreshToken: tokens.refreshToken);
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

  Future<void> logout() async {
    final access = state.accessToken;
    final refresh = state.refreshToken;
    if (access != null && refresh != null) {
      await _api.logout(access, refresh);
    }
    await _store.clear();
    state = const AuthState(status: AuthStatus.unauthenticated);
  }
}
