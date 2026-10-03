package com.example.measurex

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

/**
 * Reference MainActivity that registers the Bluetooth Classic (SPP) scale
 * plugin (PRD §9). Copy this over the generated
 * `android/app/src/main/kotlin/com/example/measurex/MainActivity.kt` after
 * `flutter create` regenerates the platform folders (see native/README.md).
 */
class MainActivity : FlutterActivity() {
    private var classicScale: ClassicScalePlugin? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        classicScale = ClassicScalePlugin(flutterEngine.dartExecutor.binaryMessenger)
    }
}
