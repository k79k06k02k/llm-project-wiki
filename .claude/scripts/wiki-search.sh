#!/usr/bin/env bash
# wiki-search.sh — search knowledge pages under wiki/
#
# Usage:
#   wiki-search.sh <query>              # full-text search (query is a fixed string, not a regex)
#   wiki-search.sh -t <tag>             # tag filter
#   wiki-search.sh -t <tag> <query>     # tag + full-text
#   wiki-search.sh -- <query>           # after --, the query may start with - (search CLI flag text)
#
# Always excluded: index*.md, README.md (per wiki-workflow.md)

set -euo pipefail

# Locate the wiki root via git; outside a git repo, fall back to the CWD
if WIKI_ROOT=$(git -C "$(pwd)" rev-parse --show-toplevel 2>/dev/null); then
    WIKI_DIR="$WIKI_ROOT/wiki"
else
    WIKI_ROOT="$(pwd)"
    WIKI_DIR="$WIKI_ROOT/wiki"
fi

if [[ ! -d "$WIKI_DIR" ]]; then
    echo "error: wiki dir not found at $WIKI_DIR" >&2
    exit 1
fi

EXCLUDES=(-g '!index*.md' -g '!README.md')

TAG=""
QUERY=""

usage() {
    grep '^# ' "$0" | sed 's/^# //'
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -t|--tag)
            [[ -z "${2:-}" ]] && usage
            TAG="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        --)
            # Everything after -- is the query, so literal queries may start with -
            shift
            while [[ $# -gt 0 ]]; do
                if [[ -z "$QUERY" ]]; then
                    QUERY="$1"
                else
                    QUERY="$QUERY $1"
                fi
                shift
            done
            ;;
        -*)
            echo "unknown flag: $1" >&2
            usage
            ;;
        *)
            if [[ -z "$QUERY" ]]; then
                QUERY="$1"
            else
                QUERY="$QUERY $1"
            fi
            shift
            ;;
    esac
done

if [[ -z "$TAG" && -z "$QUERY" ]]; then
    usage
fi

# Candidate page set
if [[ -n "$TAG" ]]; then
    # Match tags against explicit delimiters, since \b fails on hyphenated tags
    # (searching 'asset' must not hit 'asset-loading' / 'asset-import')
    CANDIDATES=$(rg -l "^tags:.*(\[|, )${TAG}(,|\])" "$WIKI_DIR" "${EXCLUDES[@]}" || true)
    if [[ -z "$CANDIDATES" ]]; then
        echo "no pages match tag: $TAG" >&2
        exit 0
    fi
else
    # The wiki is flat; maxdepth 1 with index*/README excluded is the full set
    CANDIDATES=$(find "$WIKI_DIR" -maxdepth 1 -type f -name '*.md' \
        ! -name 'index*.md' ! -name 'README.md')
fi

# With no query, just list the tag-filtered results
if [[ -z "$QUERY" ]]; then
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        title=$(awk '/^title:/ {sub(/^title: */, ""); print; exit}' "$f")
        tags=$(awk '/^tags:/ {sub(/^tags: */, ""); print; exit}' "$f")
        relpath=${f#"$WIKI_ROOT/"}
        echo "$relpath"
        [[ -n "$title" ]] && echo "  title: $title"
        [[ -n "$tags" ]] && echo "  tags: $tags"
        echo ""
    done <<< "$CANDIDATES"
    exit 0
fi

# Full-text search within the candidate pages
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    # -- stops rg's own option parsing in case QUERY starts with -
    match=$(rg -n --max-count 1 -F -i -- "$QUERY" "$f" || true)
    [[ -z "$match" ]] && continue
    title=$(awk '/^title:/ {sub(/^title: */, ""); print; exit}' "$f")
    tags=$(awk '/^tags:/ {sub(/^tags: */, ""); print; exit}' "$f")
    relpath=${f#"$WIKI_ROOT/"}
    echo "$relpath"
    [[ -n "$title" ]] && echo "  title: $title"
    [[ -n "$tags" ]] && echo "  tags: $tags"
    echo "  match: $match"
    echo ""
done <<< "$CANDIDATES"
