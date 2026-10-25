with open('molt/web/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix line 89 in mapVersion
old_line_89 = 'state: version.status === "ACTIVE" ? "active" : version.status === "REJECTED" ? "rejected" : "candidate",'
new_line_89 = 'state: version.status === "ACTIVE" ? "active" : version.status === "REJECTED" ? "rejected" : version.status === "ARCHIVED" ? "archived" : "candidate",'

assert old_line_89 in content, "old_line_89 not found"
content = content.replace(old_line_89, new_line_89, 1)

# 2. In renderRecipeReview, prefer active version
old_review_pick = 'const version = candidate || active || rejected;'
new_review_pick = 'const version = active || candidate || rejected || state.versions[0];'

assert old_review_pick in content, "old_review_pick not found"
content = content.replace(old_review_pick, new_review_pick, 1)

with open('molt/web/app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed mapVersion and review version selection successfully!")
