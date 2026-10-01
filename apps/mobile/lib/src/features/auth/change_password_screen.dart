import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../l10n/app_localizations.dart';
import 'auth_controller.dart';

class ChangePasswordScreen extends ConsumerStatefulWidget {
  const ChangePasswordScreen({super.key});

  @override
  ConsumerState<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends ConsumerState<ChangePasswordScreen> {
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirm = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final t = AppLocalizations.of(context);
    setState(() => _error = null);
    if (_next.text.length < 8) {
      setState(() => _error = t.passwordTooShort);
      return;
    }
    if (_next.text != _confirm.text) {
      setState(() => _error = t.passwordsDoNotMatch);
      return;
    }
    setState(() => _busy = true);
    final code = await ref
        .read(authControllerProvider.notifier)
        .changePassword(_current.text, _next.text);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = code == null ? null : t.genericError;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(t.changePasswordTitle)),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(t.changePasswordHint),
              const SizedBox(height: 24),
              _field(_current, t.currentPassword),
              const SizedBox(height: 16),
              _field(_next, t.newPassword),
              const SizedBox(height: 16),
              _field(_confirm, t.confirmPassword),
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(_error!, style: const TextStyle(color: Colors.red)),
              ],
              const SizedBox(height: 24),
              SizedBox(
                height: 56,
                child: FilledButton(
                  onPressed: _busy ? null : _submit,
                  child: Text(_busy ? t.saving : t.save),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _field(TextEditingController c, String label) {
    return TextField(
      controller: c,
      obscureText: true,
      decoration: InputDecoration(labelText: label, border: const OutlineInputBorder()),
    );
  }
}
