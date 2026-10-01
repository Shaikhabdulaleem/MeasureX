import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import '../../l10n/app_localizations.dart';
import 'capture_controller.dart';
import 'review_screen.dart';
import 'widgets.dart';

/// Manual L/W/H entry (cm) + mandatory photo (PRD §4 fallback, §5, §6).
class ManualDimensionsScreen extends ConsumerStatefulWidget {
  const ManualDimensionsScreen({super.key});

  @override
  ConsumerState<ManualDimensionsScreen> createState() => _ManualDimensionsScreenState();
}

class _ManualDimensionsScreenState extends ConsumerState<ManualDimensionsScreen> {
  final _formKey = GlobalKey<FormState>();
  final _length = TextEditingController();
  final _width = TextEditingController();
  final _height = TextEditingController();
  Uint8List? _photo;
  bool _photoTouched = false;

  @override
  void dispose() {
    _length.dispose();
    _width.dispose();
    _height.dispose();
    super.dispose();
  }

  int get _minCm => ref.read(effectiveConfigProvider).valueOrNull?.minDimensionCm ?? 1;
  int get _maxCm => ref.read(effectiveConfigProvider).valueOrNull?.maxDimensionCm ?? 300;

  String? _validateDim(String? value, AppLocalizations l10n) {
    final text = value?.trim() ?? '';
    final parsed = double.tryParse(text);
    if (parsed == null) return '${l10n.eachSide} $_minCm–$_maxCm cm';
    if (parsed < _minCm || parsed > _maxCm) return '${l10n.eachSide} $_minCm–$_maxCm cm';
    return null;
  }

  Future<void> _takePhoto() async {
    final picker = ImagePicker();
    final file = await picker.pickImage(
      source: ImageSource.camera,
      maxWidth: 1600,
      maxHeight: 1600,
      imageQuality: 80,
    );
    if (file == null) return;
    final bytes = await file.readAsBytes();
    if (!mounted) return;
    setState(() {
      _photo = bytes;
      _photoTouched = true;
    });
  }

  int _toMm(TextEditingController c) => (double.parse(c.text.trim()) * 10).round();

  void _continue() {
    setState(() => _photoTouched = true);
    final valid = _formKey.currentState?.validate() ?? false;
    if (!valid || _photo == null) return;

    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ReviewScreen(
          lengthMm: _toMm(_length),
          widthMm: _toMm(_width),
          heightMm: _toMm(_height),
          photoBytes: _photo!,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final number = ref.watch(captureControllerProvider).nextPackageNumber;

    return Scaffold(
      appBar: AppBar(title: Text('${l10n.measure} — ${pkgLabel(l10n, number)}')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          autovalidateMode: AutovalidateMode.onUserInteraction,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _dimField(_length, l10n.length, l10n),
              const SizedBox(height: 12),
              _dimField(_width, l10n.width, l10n),
              const SizedBox(height: 12),
              _dimField(_height, l10n.height, l10n),
              const SizedBox(height: 20),
              if (_photo != null)
                ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: Image.memory(_photo!, height: 180, fit: BoxFit.cover),
                ),
              const SizedBox(height: 8),
              SizedBox(
                height: 56,
                child: OutlinedButton.icon(
                  onPressed: _takePhoto,
                  icon: const Icon(Icons.camera_alt),
                  label: Text(_photo == null ? l10n.takePhoto : l10n.retakePhoto),
                ),
              ),
              if (_photoTouched && _photo == null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    l10n.photoRequired,
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ),
              const SizedBox(height: 24),
              SizedBox(
                height: 60,
                child: FilledButton(
                  onPressed: _continue,
                  child: Text(l10n.review),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _dimField(TextEditingController c, String label, AppLocalizations l10n) {
    return TextFormField(
      controller: c,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))],
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
        helperText: '$_minCm–$_maxCm cm',
      ),
      validator: (v) => _validateDim(v, l10n),
    );
  }
}
