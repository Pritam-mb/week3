import sqlite3

con = sqlite3.connect('workspace/molt.sqlite3')
cur = con.cursor()
cur.execute("UPDATE recipe_versions SET status = 'ARCHIVED' WHERE id = 'ver_f2ee805bdda34e32'")
cur.execute("UPDATE repair_proposals SET status = 'SUPERSEDED' WHERE id = 'repair_8e3ebdb4641c49e6'")
con.commit()
print("Cleaned up stale proposal and version successfully!")

# Verify active versions and proposals
auto_id = 'auto_d571a2f79bb14567'
print('=== ACTIVE VERSION ===')
for r in cur.execute("SELECT id, active_version_id FROM automations WHERE id = ?", (auto_id,)).fetchall():
    print(r)
print('=== REMAINING VERSIONS ===')
for r in cur.execute("SELECT id, version_number, status FROM recipe_versions WHERE automation_id = ?", (auto_id,)).fetchall():
    print(r)
print('=== REMAINING PROPOSALS ===')
for r in cur.execute("SELECT id, status FROM repair_proposals WHERE automation_id = ?", (auto_id,)).fetchall():
    print(r)
