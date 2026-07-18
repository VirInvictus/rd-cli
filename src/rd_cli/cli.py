import argparse
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from rd_cli import api

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rd",
        description="Raindrop.io CLI Client"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- Raindrops ---
    
    # list
    list_parser = subparsers.add_parser("list", help="List raindrops")
    list_parser.add_argument("-c", "--collection", type=int, default=0, help="Collection ID (0 for Unsorted, default: 0)")
    list_parser.add_argument("-s", "--search", type=str, default="", help="Search query")
    list_parser.add_argument("--page", type=int, default=0, help="Page number")
    list_parser.add_argument("--perpage", type=int, default=50, help="Items per page")
    list_parser.add_argument("-d", "--detailed", action="store_true", help="Show descriptions and tags")

    # view
    view_parser = subparsers.add_parser("view", help="View a single raindrop in detail")
    view_parser.add_argument("id", type=int, help="Raindrop ID")

    # add
    add_parser = subparsers.add_parser("add", help="Add a new raindrop")
    add_parser.add_argument("url", help="URL to bookmark")
    add_parser.add_argument("-t", "--title", help="Custom title")
    add_parser.add_argument("-c", "--collection", type=int, default=0, help="Collection ID")
    add_parser.add_argument("--tags", nargs="*", help="Tags for the bookmark")
    add_parser.add_argument("--excerpt", type=str, help="Excerpt text")
    add_parser.add_argument("--note", type=str, help="Note text")
    add_parser.add_argument("--important", action="store_true", help="Mark as important")

    # edit
    edit_parser = subparsers.add_parser("edit", help="Edit a raindrop")
    edit_parser.add_argument("id", type=int, help="Raindrop ID")
    edit_parser.add_argument("-t", "--title", help="New title")
    edit_parser.add_argument("--tags", nargs="*", help="New tags")
    edit_parser.add_argument("-c", "--collection", type=int, help="Move to collection ID")
    edit_parser.add_argument("--note", type=str, help="New note")

    # rm
    rm_parser = subparsers.add_parser("rm", help="Remove a raindrop")
    rm_parser.add_argument("id", type=int, help="Raindrop ID")

    # --- Collections ---
    
    # c-list
    c_list = subparsers.add_parser("c-list", help="List all collections")
    
    # c-add
    c_add = subparsers.add_parser("c-add", help="Add a collection")
    c_add.add_argument("title", help="Collection title")
    c_add.add_argument("--parent", type=int, help="Parent collection ID")
    
    # c-rm
    c_rm = subparsers.add_parser("c-rm", help="Remove a collection")
    c_rm.add_argument("id", type=int, help="Collection ID")

    # --- Tags ---
    
    # t-list
    t_list = subparsers.add_parser("t-list", help="List all tags")
    
    # t-rm
    t_rm = subparsers.add_parser("t-rm", help="Remove tags")
    t_rm.add_argument("tags", nargs="+", help="Tags to remove")

    # --- Highlights ---
    
    # h-list
    h_list = subparsers.add_parser("h-list", help="List highlights")
    h_list.add_argument("-r", "--raindrop", type=int, help="Specific Raindrop ID to list highlights for")
    
    # h-add
    h_add = subparsers.add_parser("h-add", help="Add highlight to a raindrop")
    h_add.add_argument("raindrop", type=int, help="Raindrop ID")
    h_add.add_argument("text", type=str, help="Text to highlight")
    h_add.add_argument("--color", type=str, default="yellow", help="Highlight color")
    h_add.add_argument("--note", type=str, default="", help="Note for highlight")
    
    # h-rm
    h_rm = subparsers.add_parser("h-rm", help="Remove highlight from raindrop")
    h_rm.add_argument("raindrop", type=int, help="Raindrop ID")
    h_rm.add_argument("highlight", type=str, help="Highlight ID")

    return parser

def main(argv: list[str] | None = None) -> int:
    env_paths = [
        Path.cwd() / ".env",
        Path.home() / ".config" / "rd-cli" / ".env",
        Path.home() / ".gitrepos" / "rd-cli" / ".env"
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break
            
    if argv is None:
        argv = sys.argv[1:]
    
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0

    args = parser.parse_args(argv)

    try:
        # Raindrops
        if args.command == "list":
            items = api.get_raindrops(collection_id=args.collection, search=args.search, page=args.page, perpage=args.perpage)
            if not items:
                print("No raindrops found.")
            for item in items:
                print(f"[{item['_id']}] {item.get('title', 'No Title')} - {item['link']}")
                if getattr(args, "detailed", False):
                    if item.get('excerpt'): print(f"  Description: {item.get('excerpt')}")
                    if item.get('note'): print(f"  Note: {item.get('note')}")
                    if item.get('tags'): print(f"  Tags: {', '.join(item.get('tags'))}")

        elif args.command == "view":
            item = api.get_raindrop(args.id)
            if not item:
                print("Raindrop not found.")
                return 1
            print(f"[{item.get('_id')}] {item.get('title', 'No Title')}")
            print(f"Link: {item.get('link')}")
            if item.get('excerpt'): print(f"Description: {item.get('excerpt')}")
            if item.get('note'): print(f"Note: {item.get('note')}")
            if item.get('tags'): print(f"Tags: {', '.join(item.get('tags'))}")
            collection_id = item.get('collectionId') or item.get('collection', {}).get('$id')
            if collection_id is not None: print(f"Collection: {collection_id}")

        elif args.command == "add":
            item = api.add_raindrop(args.url, title=args.title, collection_id=args.collection, tags=args.tags, excerpt=args.excerpt, note=args.note, important=args.important)
            print(f"Added raindrop: [{item.get('_id')}] {item.get('title')} - {item.get('link')}")

        elif args.command == "edit":
            item = api.edit_raindrop(args.id, title=args.title, tags=args.tags, collection_id=args.collection, note=args.note)
            print(f"Edited raindrop: [{item.get('_id')}] {item.get('title')}")

        elif args.command == "rm":
            success = api.delete_raindrop(args.id)
            if success: print(f"Successfully deleted raindrop {args.id}")
            else: print(f"Failed to delete raindrop {args.id}"); return 1

        # Collections
        elif args.command == "c-list":
            items = api.get_collections()
            for item in items:
                print(f"[{item['_id']}] {item.get('title')}")
                
        elif args.command == "c-add":
            item = api.create_collection(args.title, parent_id=args.parent)
            print(f"Created collection: [{item.get('_id')}] {item.get('title')}")
            
        elif args.command == "c-rm":
            success = api.delete_collection(args.id)
            if success: print(f"Successfully deleted collection {args.id}")
            else: print(f"Failed to delete collection {args.id}"); return 1
            
        # Tags
        elif args.command == "t-list":
            items = api.get_tags()
            for item in items:
                print(f"{item['_id']} ({item['count']})")
                
        elif args.command == "t-rm":
            success = api.delete_tags(args.tags)
            if success: print(f"Successfully deleted tags: {', '.join(args.tags)}")
            else: print(f"Failed to delete tags"); return 1
            
        # Highlights
        elif args.command == "h-list":
            if args.raindrop:
                items = api.get_raindrop_highlights(args.raindrop)
            else:
                items = api.get_all_highlights()
            for item in items:
                print(f"[{item['_id']}] (RD: {item.get('raindropRef', 'N/A')}) - {item.get('text')}")
                if item.get('note'):
                    print(f"  Note: {item.get('note')}")
                    
        elif args.command == "h-add":
            items = api.add_highlight(args.raindrop, args.text, color=args.color, note=args.note)
            print(f"Added highlight to raindrop {args.raindrop}")
            
        elif args.command == "h-rm":
            success = api.delete_highlight(args.raindrop, args.highlight)
            if success: print(f"Successfully deleted highlight {args.highlight}")
            else: print(f"Failed to delete highlight {args.highlight}"); return 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
