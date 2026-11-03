// Android application: Compose UI over :core (§16.4–16.5).
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// versionName is the Python package version; versionCode = major*10000 + minor*100 + patch (§16.7).
val pyproject = rootProject.file("../pyproject.toml")
val kertVersion =
    Regex("""(?m)^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"""")
        .find(providers.fileContents(layout.projectDirectory.file(pyproject.path)).asText.get())
        ?.destructured
        ?: error("no x.y.z version in $pyproject")

// Third-party notices (§16.7): each module on a variant's runtime classpath with the license
// its POM (or parent POM) declares, plus the full texts. An unknown license fails the build.
val licenseTexts = mapOf("Apache-2.0" to file("licenses/Apache-2.0.txt"))

fun licenseId(name: String): String? = when {
    "apache" in name.lowercase() && "2.0" in name -> "Apache-2.0"
    else -> null
}

fun pomOf(group: String, module: String, version: String): org.w3c.dom.Element? =
    dependencies.createArtifactResolutionQuery()
        .forModule(group, module, version)
        .withArtifacts(MavenModule::class.java, MavenPomArtifact::class.java)
        .execute().resolvedComponents
        .flatMap { it.getArtifacts(MavenPomArtifact::class.java) }
        .filterIsInstance<org.gradle.api.artifacts.result.ResolvedArtifactResult>()
        .firstOrNull()
        ?.let { javax.xml.parsers.DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(it.file).documentElement }

fun org.w3c.dom.Element.child(name: String): org.w3c.dom.Element? =
    (0 until childNodes.length).map { childNodes.item(it) }
        .filterIsInstance<org.w3c.dom.Element>().firstOrNull { it.tagName == name }

/** License names declared by a POM, following `<parent>` when it declares none. */
fun pomLicenses(pom: org.w3c.dom.Element?): List<String> {
    pom ?: return emptyList()
    val names = pom.child("licenses")?.getElementsByTagName("name")
        ?.let { list -> (0 until list.length).map { list.item(it).textContent.trim() } }.orEmpty()
    if (names.isNotEmpty()) return names
    val parent = pom.child("parent") ?: return emptyList()
    return pomLicenses(
        pomOf(
            parent.child("groupId")!!.textContent.trim(),
            parent.child("artifactId")!!.textContent.trim(),
            parent.child("version")!!.textContent.trim(),
        ),
    )
}

fun notices(classpath: String): Map<String, String> =
    configurations.getByName(classpath).incoming.resolutionResult.allComponents
        .mapNotNull { it.id as? org.gradle.api.artifacts.component.ModuleComponentIdentifier }
        .sortedBy { it.displayName }
        .mapNotNull { id ->
            val pom = pomOf(id.group, id.module, id.version)
            val names = pomLicenses(pom)
            // A BOM or other POM-only module ships no code.
            if (names.isEmpty() && pom?.child("packaging")?.textContent?.trim() == "pom") return@mapNotNull null
            val license = names.firstNotNullOfOrNull(::licenseId)
                ?: error("${id.displayName}: no known license in its POM ($names); add its text to app/licenses")
            id.displayName to license
        }
        .toMap()

abstract class ThirdPartyNotices : DefaultTask() {
    @get:Input abstract val modules: MapProperty<String, String>
    @get:Input abstract val texts: MapProperty<String, String>
    @get:InputFile abstract val kertLicense: RegularFileProperty
    @get:OutputDirectory abstract val outputDir: DirectoryProperty

    @TaskAction
    fun write() {
        val used = modules.get().values.toSortedSet()
        val text = buildString {
            appendLine("kert for Android is released under the MIT License (below).")
            appendLine("It bundles these third-party libraries:")
            appendLine()
            modules.get().forEach { (module, license) -> appendLine("$module  $license") }
            used.forEach { appendLine("\n==== $it ====\n"); append(texts.get().getValue(it)) }
            appendLine("\n==== kert ====\n")
            append(kertLicense.get().asFile.readText())
        }
        outputDir.get().file("third_party_notices.txt").asFile.writeText(text)
    }
}

androidComponents {
    onVariants { variant ->
        val task = tasks.register<ThirdPartyNotices>("${variant.name}ThirdPartyNotices") {
            modules.set(provider { notices("${variant.name}RuntimeClasspath") })
            texts.set(licenseTexts.mapValues { it.value.readText() })
            kertLicense.set(rootProject.file("../LICENSE"))
        }
        variant.sources.assets?.addGeneratedSourceDirectory(task, ThirdPartyNotices::outputDir)
    }
}

// Release signing comes from CI (§16.7); without a keystore the release APK stays unsigned.
val keystore = providers.environmentVariable("KERT_ANDROID_KEYSTORE").orNull

android {
    namespace = "io.github.myarzik.kert.app"
    compileSdk = 37 // Compose 1.12 (BOM 2026.09) requires compiling against API 37+

    defaultConfig {
        applicationId = "io.github.myarzik.kert"
        minSdk = 26
        targetSdk = 36
        val (major, minor, patch) = kertVersion
        versionCode = major.toInt() * 10000 + minor.toInt() * 100 + patch.toInt()
        versionName = "$major.$minor.$patch"
    }

    if (keystore != null) {
        signingConfigs.create("release") {
            storeFile = file(keystore)
            storePassword = providers.environmentVariable("ANDROID_KEYSTORE_PASSWORD").get()
            keyAlias = providers.environmentVariable("ANDROID_KEY_ALIAS").get()
            keyPassword = providers.environmentVariable("ANDROID_KEY_PASSWORD").get()
        }
        buildTypes.getByName("release").signingConfig = signingConfigs.getByName("release")
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
                it.systemProperty("kert.pyproject", pyproject.path)
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
