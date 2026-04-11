import pathlib
import re

WIKI_DIR = pathlib.Path(__file__).parent.parent / "wiki"


def get_all_filenames():
    mapping = {}
    for f in WIKI_DIR.glob("**/*.md"):
        stem = f.stem
        mapping[stem.lower()] = stem
    return mapping

def find_best_match(link_name, filename_map):

    # 1. 完全匹配
    if link_name.lower() in filename_map:
        return filename_map[link_name.lower()]
    # 2. 包含匹配
    candidates = []
    for key, original in filename_map.items():
        if link_name.lower() in key or key in link_name.lower():
            candidates.append((original, key))
    if len(candidates) == 1:
        return candidates[0][0]
    # 3. 词汇重叠匹配
    link_words = set(link_name.lower().split())
    best_score = 0
    best_match = None
    for key, original in filename_map.items():
        file_words = set(key.split())
        overlap = len(link_words & file_words)
        if overlap > best_score:
            best_score = overlap
            best_match = original
    if best_score >= 1:
        return best_match
    return None

def fix_links_in_file(filepath, filename_map, broken_set, dry_run=True):
    content = filepath.read_text(encoding="utf-8")
    # 匹配普通链接 [[name]] 和别名链接 [[name|alias]]
    pattern = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')
    replacements = {}
    for match in pattern.finditer(content):
        link_name = match.group(1).strip()
        alias = match.group(2)
        original_full = match.group(0)
        if link_name in filename_map.values():
            continue
        best = find_best_match(link_name, filename_map)
        if best and best != link_name:
            # 保留alias如果有的话
            if alias:
                new_link = f"[[{best}|{alias}]]"
            else:
                new_link = f"[[{best}]]"
            replacements[original_full] = new_link
    if not replacements:
        return 0

    print(f"\n{filepath.name}:")
    for old, new in replacements.items():
        print(f"  {old} → {new}")
    if not dry_run:
        new_content = content
        for old, new in replacements.items():
            new_content = new_content.replace(old, new)
        filepath.write_text(new_content, encoding="utf-8")
    return len(replacements)

def get_broken_links(filename_map):
    broken = set()
    pattern = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]')
    for f in WIKI_DIR.glob("**/*.md"):
        for match in pattern.finditer(f.read_text(encoding="utf-8")):
            link_name = match.group(1).strip()
            if link_name not in filename_map.values():
                broken.add(link_name)
    return broken

def fix_all_links(dry_run=True):
    filename_map = get_all_filenames()
    print(f"Found {len(filename_map)} wiki articles")

    broken_set = get_broken_links(filename_map)

    if dry_run:
        print("\n=== DRY RUN (preview only, no changes made) ===")
    else:
        print("\n=== APPLYING FIXES ===")

    total = 0
    for f in WIKI_DIR.glob("**/*.md"):
        count = fix_links_in_file(f, filename_map, broken_set, dry_run=dry_run)
        total += count

    print(f"\nTotal links to fix: {total}")

    # 显示仍然无法修复的链接
    remaining_broken = get_broken_links(filename_map)
    if remaining_broken:
        print(f"\nStill broken ({len(remaining_broken)}) — no matching article found:")
        for b in sorted(remaining_broken):
            print(f"  [[{b}]]")

    if dry_run and total > 0:
        confirm = input("\nApply these fixes? (yes/no): ").strip().lower()
        if confirm == "yes":
            fix_all_links(dry_run=False)
            print("All links fixed!")
        else:
            print("Cancelled.")

if __name__ == "__main__":
    fix_all_links(dry_run=True)