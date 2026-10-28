// Android application: Compose UI over :core (§16.4–16.5).
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
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
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation(project(":core"))
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.activity.compose)
}
