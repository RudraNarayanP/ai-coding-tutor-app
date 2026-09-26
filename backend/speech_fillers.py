"""Shared speech-filler fragments for the caption-dump detectors."""

# "sort of" / "kind of" are hedges in speech ("it's sort of like a list") but plain
# English after a determiner or a sort-algorithm name ("a topological sort of the
# graph", "what kind of data"). Only the hedge counts as filler: the noun use made
# validate_project throw away an AI-reviewed micrograd course (sweep 02:35 IST).
HEDGE_SORT_KIND = (
    r"(?<!\ba )(?<!\ban )(?<!\bthe )(?<!\bthis )(?<!\bthat )(?<!\bwhat )(?<!\bwhich )"
    r"(?<!\bany )(?<!\bsome )(?<!\bsame )(?<!\bone )(?<!\beach )(?<!\bevery )(?<!\banother )"
    r"(?<!\bdifferent )(?<!ical )(?<!\bmerge )(?<!\bquick )(?<!\bbubble )(?<!\bstable )"
    r"(?<!\bheap )(?<!\bradix )(?<!\binsertion )(?<!\bselection )(?<!\btopo )"
    r"(?:sort|kind) of"
)
