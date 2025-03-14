import sqlite3
import pyodbc
import os
import decimal

# MSSQL Connection
MSSQL_CONN_STR = os.getenv('OpenOrchestratorSQL')
sqlite_db_path = "pyorchestrator_test.db"

def clone_mssql_to_sqlite():
    # Connect to MSSQL
    mssql_conn = pyodbc.connect(MSSQL_CONN_STR)
    mssql_cursor = mssql_conn.cursor()

    # Connect to SQLite
    if os.path.exists(sqlite_db_path):
        os.remove(sqlite_db_path)  # Remove existing DB to start fresh
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_cursor = sqlite_conn.cursor()

    # Get all tables
    mssql_cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
    tables = [row[0] for row in mssql_cursor.fetchall()]

    for table in tables:
        print(f"Cloning {table}...")

        # Get column info
        mssql_cursor.execute(f"""
            SELECT COLUMN_NAME, DATA_TYPE 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = '{table}'
        """)
        columns = mssql_cursor.fetchall()

        # Get primary key column(s)
        mssql_cursor.execute(f"""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
            WHERE TABLE_NAME = '{table}' AND OBJECTPROPERTY(OBJECT_ID(CONSTRAINT_SCHEMA + '.' + CONSTRAINT_NAME), 'IsPrimaryKey') = 1
        """)
        primary_keys = [row[0] for row in mssql_cursor.fetchall()]

        column_defs = []
        for col_name, col_type in columns:
            if col_type in ('int', 'bigint', 'tinyint', 'smallint'):
                sqlite_type = 'INTEGER'
            elif col_type in ('nvarchar', 'varchar', 'text', 'uniqueidentifier'):  # UUIDs should be TEXT
                sqlite_type = 'TEXT'
            elif col_type in ('datetime', 'smalldatetime', 'date', 'time'):
                sqlite_type = 'TEXT'  # Store dates as TEXT
            elif col_type == 'bit':
                sqlite_type = 'INTEGER'  # SQLite uses 0/1 for boolean
            elif col_type in ('decimal', 'numeric', 'float', 'real'):
                sqlite_type = 'REAL'  # Convert decimal to float
            else:
                sqlite_type = 'TEXT'  # Default to text

            column_defs.append(f'"{col_name}" {sqlite_type}')
        
        # Append primary key constraint
        if primary_keys:
            pk_statement = f", PRIMARY KEY ({', '.join([f'\"{pk}\"' for pk in primary_keys])})"
        else:
            pk_statement = ""

        # Create table in SQLite
        create_table_sql = f'CREATE TABLE "{table}" ({", ".join(column_defs)}{pk_statement})'
        sqlite_cursor.execute(create_table_sql)

        # Copy data
        mssql_cursor.execute(f"SELECT * FROM {table}")
        rows = mssql_cursor.fetchall()
        placeholders = ", ".join("?" * len(columns))
        insert_sql = f'INSERT INTO "{table}" VALUES ({placeholders})'

        for row in rows:
            # Convert Decimal values to float
            converted_row = tuple(float(val) if isinstance(val, decimal.Decimal) else val for val in row)
            sqlite_cursor.execute(insert_sql, converted_row)

        sqlite_conn.commit()
    
    mssql_conn.close()
    sqlite_conn.close()

if __name__ == "__main__":
    clone_mssql_to_sqlite()
