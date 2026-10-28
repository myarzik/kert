package io.github.myarzik.kert.app

import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import io.github.myarzik.kert.core.SqlConnection
import java.io.File

/** Android's SQLite behind the core [SqlConnection] seam (§16.3). */
class AndroidSqlConnection private constructor(private val db: SQLiteDatabase) : SqlConnection {
    override fun query(sql: String, vararg args: Any?): List<List<Any?>> =
        db.rawQuery(sql, args.map { it?.toString() }.toTypedArray()).use { cursor ->
            buildList {
                while (cursor.moveToNext()) add((0 until cursor.columnCount).map { cursor.value(it) })
            }
        }

    override fun execute(sql: String, vararg args: Any?) =
        if (args.isEmpty()) db.execSQL(sql) else db.execSQL(sql, args)

    override fun close() = db.close()

    private fun Cursor.value(column: Int): Any? = when (getType(column)) {
        Cursor.FIELD_TYPE_NULL -> null
        Cursor.FIELD_TYPE_INTEGER -> getLong(column)
        Cursor.FIELD_TYPE_FLOAT -> getDouble(column)
        Cursor.FIELD_TYPE_BLOB -> getBlob(column)
        else -> getString(column)
    }

    companion object {
        /** Read-write, keeping the file's WAL journal mode (D8). */
        fun open(file: File): AndroidSqlConnection = AndroidSqlConnection(
            SQLiteDatabase.openDatabase(
                file.path,
                null,
                SQLiteDatabase.OPEN_READWRITE or SQLiteDatabase.ENABLE_WRITE_AHEAD_LOGGING,
            ),
        )
    }
}
