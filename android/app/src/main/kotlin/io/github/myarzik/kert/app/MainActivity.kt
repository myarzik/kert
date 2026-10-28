package io.github.myarzik.kert.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.Text
import io.github.myarzik.kert.core.KertFormat

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Placeholder until the library and reader screens land (§16.8, tasks 22–23).
        setContent { Text("kert · .kert format ${KertFormat.SCHEMA_VERSION}") }
    }
}
