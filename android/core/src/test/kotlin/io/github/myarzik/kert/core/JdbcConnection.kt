package io.github.myarzik.kert.core

import java.nio.file.Path
import java.sql.Connection
import java.sql.DriverManager

/** Test-only [SqlConnection] over JDBC SQLite; the app uses Android's SQLite. */
class JdbcConnection(path: Path) : SqlConnection {
    private val connection: Connection = DriverManager.getConnection("jdbc:sqlite:$path")

    override fun query(sql: String, vararg args: Any?): List<List<Any?>> =
        connection.prepareStatement(sql).use { statement ->
            args.forEachIndexed { i, arg -> statement.setObject(i + 1, arg) }
            statement.executeQuery().use { rs ->
                val columns = rs.metaData.columnCount
                buildList {
                    while (rs.next()) add((1..columns).map { rs.getObject(it) })
                }
            }
        }

    override fun execute(sql: String, vararg args: Any?) {
        connection.prepareStatement(sql).use { statement ->
            args.forEachIndexed { i, arg -> statement.setObject(i + 1, arg) }
            statement.execute()
        }
    }

    override fun close() = connection.close()
}
