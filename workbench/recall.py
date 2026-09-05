"""Read-only batch adapter. Ranking stays in tools/mapper.py; IDs are scoped by core.mjs."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
from mapper import load, build_df, score  # noqa: E402


def recall(request):
    allowed = set(request['ids'])
    anchors = [a for a in load() if a['id'] in allowed]
    df, n = build_df(anchors)
    out = []
    for task in request['tasks']:
        found = []
        for anchor in anchors:
            match = score(task['text'], anchor, '科学', request['grade'], df, n)
            if match:
                value, runs = match
                found.append((value, anchor['id'], [term for term, _ in runs[:6]]))
        found.sort(key=lambda item: (-item[0], item[1]))
        out.append({'id': task['id'], 'candidates': [
            {'id': aid, 'terms': terms} for _, aid, terms in found[:request['limit']]
        ]})
    return out


if __name__ == '__main__':
    print(json.dumps(recall(json.load(sys.stdin)), ensure_ascii=False))
