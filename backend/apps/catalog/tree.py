"""Category trees. Pure Python."""

from collections.abc import Mapping, Sequence


def with_descendants(children_by_parent: Mapping[int | None, Sequence[int]], root: int) -> set[int]:
    """`root` and every category below it. Safe against a loop in bad data."""
    seen = {root}
    stack = [root]
    while stack:
        for child in children_by_parent.get(stack.pop(), ()):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen
