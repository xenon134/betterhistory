from collections import namedtuple
import datetime
import os
import sqlite3
import sys

DB_FILE_original = r"C:\Users\deep\AppData\Local\BraveSoftware\Brave-Browser\User Data\Default\History"

# create temporary copy to avoid locking issues
with open(DB_FILE_original, "rb") as original_db:
    db_bytes = original_db.read()
import tempfile
with tempfile.NamedTemporaryFile(mode="w+b", delete=False) as temp_file:
    temp_file.write(db_bytes)
    db_file = temp_file.name

# 1. Connect to the database
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

cursor.execute("SELECT url, title, visit_count, last_visit_time FROM urls ORDER BY last_visit_time DESC")
column_names = [info[0] for info in cursor.description]
URLnt = namedtuple('URLnt', column_names)
urls = [URLnt(*i) for i in cursor.fetchall()]

conn.close()
os.unlink(db_file)  # remove temporary file

if len(sys.argv) > 1:
    outfile = sys.argv[1]
else:
    outfile = "C:\\Users\\deep\\Desktop\\brave_history.txt"
    print('Defaulting to', outfile)

with open(outfile, "a", encoding="utf-8") as f:
    for i in urls:
        if i.last_visit_time:  # is not 0
            timestamp = datetime.datetime.fromtimestamp(i.last_visit_time/1e6 - 11644473600)
        else:
            timestamp = 'UNKNOWN'
        print(f"{i.title} [{i.visit_count}]", i.url, timestamp, '',
            sep='\n', file=f, flush=False)  # flush at the very end

print('Wrote', len(urls), 'entries.')
