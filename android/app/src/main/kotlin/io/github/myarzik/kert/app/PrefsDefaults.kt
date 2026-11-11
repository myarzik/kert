package io.github.myarzik.kert.app

import android.content.Context
import io.github.myarzik.kert.core.Reader
import io.github.myarzik.kert.core.SettingsDefaults
import io.github.myarzik.kert.core.Theme

/** App-wide setting defaults, the TOML layer of §8.4 on Android (§16.5). */
class PrefsDefaults(context: Context) : SettingsDefaults {
    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)

    override val chunkWidth: Int?
        get() = prefs.getString("chunk_width", null)?.toIntOrNull()
            ?.takeIf { it in Reader.WIDTH_MIN..Reader.WIDTH_MAX }

    override val theme: Theme?
        get() = prefs.getString("theme", null)?.let { v -> Theme.entries.find { it.storage == v } }

    override val recap: Boolean? get() = switch("recap")

    override val recall: Boolean? get() = switch("recall")

    private fun switch(key: String): Boolean? = when (prefs.getString(key, null)) {
        "on" -> true
        "off" -> false
        else -> null
    }

    override fun save(key: String, value: String) = prefs.edit().putString(key, value).apply()
}
