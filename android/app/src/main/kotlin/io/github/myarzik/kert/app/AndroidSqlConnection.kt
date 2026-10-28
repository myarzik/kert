package io.github.myarzik.kert.app

import io.github.myarzik.kert.core.SqlConnection
import java.io.File

class AndroidSqlConnection private constructor() : SqlConnection {
    override fun query(sql: String, vararg args: Any?): List<List<Any?>> = TODO("task 22")

    override fun execute(sql: String, vararg args: Any?): Unit = TODO("task 22")

    override fun close(): Unit = TODO("task 22")

    companion object {
        fun open(file: File): AndroidSqlConnection = TODO("task 22")
    }
}
