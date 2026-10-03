import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/app_localizations.dart';
import 'scale_controller.dart';
import 'scale_ui.dart';

/// Test weight screen (PRD §9): shows the live value and state so a station can
/// confirm its scale before using it. Also hosts the hidden HID capture field.
class TestWeightScreen extends ConsumerStatefulWidget {
  const TestWeightScreen({super.key});

  @override
  ConsumerState<TestWeightScreen> createState() => _TestWeightScreenState();
}

class _TestWeightScreenState extends ConsumerState<TestWeightScreen> {
  @override
  void initState() {
    super.initState();
    // Ensure we are connected when the screen opens.
    final controller = ref.read(scaleControllerProvider.notifier);
    if (!ref.read(scaleControllerProvider).isConnected) {
      WidgetsBinding.instance.addPostFrameCallback((_) => controller.connect());
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final runtime = ref.watch(scaleControllerProvider);
    final controller = ref.read(scaleControllerProvider.notifier);
    final color = scaleStateColor(context, runtime.state);
    final grams = runtime.grams;

    return Scaffold(
      appBar: AppBar(title: Text(l10n.testWeight)),
      body: Stack(
        children: [
          // Hidden field that receives HID-keyboard scale input, when relevant.
          HidCaptureField(enabled: controller.hidAdapter != null),
          Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  grams != null ? '${(grams / 1000).toStringAsFixed(2)} kg' : '—',
                  style: Theme.of(context)
                      .textTheme
                      .displayMedium
                      ?.copyWith(fontWeight: FontWeight.bold, color: color),
                ),
                const SizedBox(height: 12),
                Text(scaleStateLabel(l10n, runtime.state),
                    style: TextStyle(fontSize: 18, color: color)),
                const SizedBox(height: 32),
                if (controller.simulatedAdapter != null)
                  OutlinedButton.icon(
                    onPressed: () => controller.simulatedAdapter!.simulateDisconnect(),
                    icon: const Icon(Icons.bluetooth_disabled),
                    label: Text(l10n.disconnect),
                  ),
                TextButton.icon(
                  onPressed: () => controller.tare(),
                  icon: const Icon(Icons.exposure_zero),
                  label: Text(l10n.tare),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// An off-screen, always-focused text field that forwards complete lines (the
/// scale "types" the weight then Enter) to the HID adapter (PRD §9).
class HidCaptureField extends ConsumerStatefulWidget {
  const HidCaptureField({super.key, required this.enabled});
  final bool enabled;

  @override
  ConsumerState<HidCaptureField> createState() => _HidCaptureFieldState();
}

class _HidCaptureFieldState extends ConsumerState<HidCaptureField> {
  final _controller = TextEditingController();
  final _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    if (widget.enabled) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _focus.requestFocus());
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _onSubmitted(String line) {
    ref.read(scaleControllerProvider.notifier).hidAdapter?.submitLine(line);
    _controller.clear();
    _focus.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) return const SizedBox.shrink();
    // Zero-size but focused so the HID scale's keystrokes land here.
    return Offstage(
      offstage: true,
      child: TextField(
        controller: _controller,
        focusNode: _focus,
        autofocus: true,
        onSubmitted: _onSubmitted,
      ),
    );
  }
}
