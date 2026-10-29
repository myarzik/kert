// Android application: Compose UI over :core (§16.4–16.5).
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.chaquopy)
}

android {
    namespace = "io.github.myarzik.kert.app"
    compileSdk = 37 // Compose 1.12 (BOM 2026.09) requires compiling against API 37+

    defaultConfig {
        applicationId = "io.github.myarzik.kert"
        minSdk = 26
        targetSdk = 36
        versionCode = 200 // major*10000 + minor*100 + patch (§16.7)
        versionName = "0.2.0"

        ndk {
            // Phones are arm64; x86_64 keeps the emulator usable.
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            all {
                // Reference fixtures from the Python implementation (§16.6).
                it.systemProperty("kert.reference", rootProject.file("../build/android-reference").path)
                // Robolectric 4.17 needs exactly Java 21 for SDK 36 sandboxes.
                it.javaLauncher.set(
                    project.extensions.getByType<JavaToolchainService>().launcherFor {
                        languageVersion.set(JavaLanguageVersion.of(21))
                    },
                )
                // Its FileDescriptor interceptor uses JDK internals.
                it.jvmArgs(
                    "--add-opens=java.base/jdk.internal.access=ALL-UNNAMED",
                    "--add-opens=java.base/java.io=ALL-UNNAMED",
                )
            }
        }
    }
}

// On-device compiler (spike): the Python compiler from ../../src on Python 3.10,
// the only version with Android wheels for spaCy in the Chaquopy repository.
// The build needs `python3.10` on PATH (pip and bytecode compilation).
chaquopy {
    defaultConfig {
        version = "3.10"
        pip {
            install("spacy==3.8.7")
            install("click") // spaCy's CLI imports it; newer typer no longer pulls it in
            install("markdown-it-py==4.2.0")
            // msgpack ships only an sdist with a C extension: use the pure-Python build.
            install("wheels/msgpack-1.2.3-py3-none-any.whl")
            install("https://github.com/explosion/spacy-models/releases/download/ru_core_news_sm-3.8.0/ru_core_news_sm-3.8.0-py3-none-any.whl")
            install("https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl")
        }
    }
    sourceSets {
        getByName("main") {
            srcDir("../../src")
        }
    }
}

dependencies {
    implementation(project(":core"))
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.activity.compose)

    testImplementation(libs.junit4)
    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.test.core)
    testImplementation(libs.androidx.test.ext.junit)
    testImplementation(platform(libs.compose.bom))
    testImplementation(libs.compose.ui.test.junit4)
    debugImplementation(libs.compose.ui.test.manifest)
}
