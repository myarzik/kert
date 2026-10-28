// Pure Kotlin/JVM: the reading engine, testable without the Android SDK (§16.2).
plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(libs.msgpack.core)

    testImplementation(platform(libs.junit.bom))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.junit.params)
    testRuntimeOnly(libs.junit.launcher)
    testImplementation(libs.sqlite.jdbc)
    testImplementation(libs.kotlinx.serialization.json)
}

tasks.test {
    useJUnitPlatform()
    // Reference fixtures from the Python implementation (§16.6).
    systemProperty("kert.reference", rootProject.file("../build/android-reference").path)
}
