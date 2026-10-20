plugins {
    // AGP 9 has built-in Kotlin support — the kotlin.android plugin is not applied.
    id("com.android.application")
}

android {
    namespace = "com.aymakan.measurex.m9capture"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.aymakan.measurex.m9capture"
        minSdk = 24          // ARCore requires API 24+
        targetSdk = 36
        versionCode = 1
        versionName = "0.1-research"
    }

    buildTypes {
        getByName("debug") {
            isMinifyEnabled = false
        }
        getByName("release") {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    // ARCore (metric VIO camera poses + intrinsics). No Sceneform, no depth API.
    implementation("com.google.ar:core:1.48.0")

    testImplementation("junit:junit:4.13.2")
    // kotlin.test assertions backed by the JUnit4 runner (built-in Kotlin supplies stdlib).
    testImplementation("org.jetbrains.kotlin:kotlin-test-junit:2.1.20")
    // Pure-JVM JSON parsing for the raw-manifest serialisation test.
    testImplementation("org.json:json:20240303")
}
