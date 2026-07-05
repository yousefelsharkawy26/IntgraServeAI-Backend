import sqlite3
import sqlite_vec
import struct
import os

def generate_dummy_vector(seed_value, dim=768):
    """
    Generates a dummy vector of 768 dimensions.
    """
    return [float(seed_value) / dim for _ in range(dim)]

def init_db():
    db_name = "shopeasy.db"
    if os.path.exists(db_name):
        os.remove(db_name)

    # Connect to SQLite and load the sqlite-vec extension
    conn = sqlite3.connect(db_name)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    cur = conn.cursor()
    
    # Create the vec0 virtual table
    cur.execute("CREATE VIRTUAL TABLE products_embeddings USING vec0(embedding float[768])")
    
    # Insert 3 dummy product vectors
    for i in range(1, 4):
        vector = generate_dummy_vector(i)
        vector_bytes = struct.pack(f"{len(vector)}f", *vector)
        # We explicitly set rowid to represent Product IDs 1, 2, and 3
        cur.execute("INSERT INTO products_embeddings(rowid, embedding) VALUES (?, ?)", (i, vector_bytes))
    
    conn.commit()
    conn.close()
    print(f"Successfully initialized {db_name} with sqlite-vec and 3 dummy products.")

if __name__ == "__main__":
    init_db()