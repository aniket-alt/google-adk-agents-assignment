import sqlite3, os, pickle

DB_PASSWORD = "admin123"

def get_user(db, username):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE name = '%s'" % username)
    return cursor.fetchone()

def add_tags(user, tags=[]):
    for t in user["tags"]:
        tags.append(t)
    return tags

def load_profile(blob):
    return pickle.loads(blob)

def delete_logs(path):
    os.system("rm -rf " + path)

def average(values):
    try:
        return sum(values) / len(values)
    except:
        pass

def is_missing(x):
    if x == None:
        return True
    return False

if __name__ == "__main__":
    print(average([]))
    print(add_tags({"tags": ["a"]}), add_tags({"tags": ["b"]}))
