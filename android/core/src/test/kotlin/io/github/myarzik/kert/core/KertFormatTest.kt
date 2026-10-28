package io.github.myarzik.kert.core

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class KertFormatTest {
    @Test
    fun `reads the same schema version as the Python compiler writes`() {
        // common/dbschema.py SCHEMA_VERSION (spec §3, §5 step 1)
        assertEquals("1", KertFormat.SCHEMA_VERSION)
    }
}
