# Test Coverage Gaps for Matching Pipeline

This document identifies missing test coverage for the matching pipeline and recommends specific test cases to add.

## Known Gaps (from matching-pipeline-test-coverage.md)

### 1. Cyclic or Chained `related_result_id` Graphs (store_report.py)

**Issue:** `_resolved_anchors` walks result chains A→B→C→...→canonical but has no test coverage for:
- Cycles: A→B→C→A
- Long chains: A→B→C→D→E (3+ hops)
- Chains with breaks: A→B→C→NULL

**Risk:** Suspected to produce start-node-dependent results or infinite loops in cyclic cases.

**Test Case:**
```python
def test_resolved_anchors_detects_cycle():
    # Result 1: related_result_id = 2
    # Result 2: related_result_id = 3
    # Result 3: related_result_id = 1 (cycle back)
    # Confirm _resolved_anchors exits without hanging
    # Verify each result's anchor is consistent

def test_resolved_anchors_long_chain():
    # A→B→C→D→E chain
    # Confirm all resolve to E (or lowest canonical)
    # Verify deterministic regardless of iteration order

def test_resolved_anchors_chain_with_missing_link():
    # A→B→C→NULL (C points to non-existent result)
    # Confirm loop stops at NULL
    # Verify remaining results have correct anchors
```

### 2. Confidence Erosion on Cluster Merge (store_report.py)

**Issue:** When a low-confidence new link merges into a high-confidence existing cluster, `weakest_confidence` applies downgrade uniformly across the whole cluster.

**Risk:** Previously-established high-confidence signal eroded by new low-confidence match. Unclear if intentional.

**Test Case:**
```python
def test_confidence_erosion_on_cluster_merge():
    # Cluster 1: results [10, 11] with confidence "high"
    # Cluster 2: results [20, 21] with confidence "high"
    # New job 30 matches result 10 (from cluster 1) with confidence "low"
    # New job 30 matches result 20 (from cluster 2) with confidence "low"
    # Confirm: merged cluster confidence is "low" (erosion applied)
    # Note: verify this is intentional per design docs

def test_confidence_preservation_same_confidence_merge():
    # Two clusters both with "high" confidence merge
    # Confirm merged cluster remains "high"
```

### 3. Double Failure in Representative Recovery (orchestrator.py)

**Issue:** When representative fails and first retry candidate also fails before second candidate succeeds, the first candidate's dupe entry gets reassigned to the second candidate (correct), but the first candidate's own failed result row should stay independent.

**Risk:** Dupe entry for failed candidate 1 points to candidate 2 instead of staying independent.

**Test Case:**
```python
def test_double_failed_representative_recovery():
    # Representative 100 fails (result row exists with status "failed")
    # Retry candidate 101 fails (result row exists with status "failed")
    # Retry candidate 102 succeeds (becomes new representative)
    # Confirm:
    #   - Dupe[job=100] → representative_job_id=102
    #   - Dupe[job=101] → representative_job_id=102 (or stays at 100?)
    #   - Result rows 100, 101, 102 all exist with correct status
    #   - Final representative is 102
    # Verify correct state per design intent
```

## Additional Gaps (Repository-Wide)

### Text Similarity Threshold Boundaries

**Tests Missing:**
- Exact threshold boundaries: 0.749999, 0.75, 0.750001 for pre-analysis same-catalog
- Cross-catalog: 0.89999, 0.90, 0.90001
- Post-analysis deterministic: 0.549999, 0.55, 0.69999, 0.70, 0.84999, 0.85

```python
def test_text_similarity_threshold_boundaries():
    # Pre-analysis same-catalog (threshold 0.75)
    result_below = score_similarity(..., stage="pre_analysis")  # 0.749
    result_at = score_similarity(..., stage="pre_analysis")     # 0.75
    result_above = score_similarity(..., stage="pre_analysis")  # 0.751
    assert result_below.confidence is None
    assert result_at.confidence == "high"
    assert result_above.confidence == "high"
```

### Generic Token Case Folding

**Tests Missing:**
- Case variations: "FAILED", "Failed", "failed", "FaIlEd" all treated as generic

```python
def test_generic_tokens_case_insensitive():
    assert _significant_tokens("FAILED timeout ERROR") == set()  # All generic
    assert _significant_tokens("failed Timeout error") == set()  # All generic
```

### Pre-Analysis Ambiguous Catalogs with 3+ Categories

**Tests Missing:**
- Current test uses 2 conflicting categories; 3+ categories should all be ambiguous

```python
def test_pre_analysis_gate_ambiguous_three_categories():
    historical = [
        {"catalog_item": "widget", "root_cause_category": "infrastructure"},
        {"catalog_item": "widget", "root_cause_category": "application_bug"},
        {"catalog_item": "widget", "root_cause_category": "configuration"},
    ]
    # All three categories conflict → widget is ambiguous
    # No historical skip-matching should occur
```

### Catalog Extraction Edge Cases

**Tests Missing:**
- Non-RHPDS format job names
- Empty/malformed names
- Whitespace handling

```python
def test_extract_catalog_item_non_standard_format():
    assert extract_catalog_item("my-job") is None
    assert extract_catalog_item("") is None
    assert extract_catalog_item("  RHPDS rhpds.widget.item.prod  ") == "widget"
    assert extract_catalog_item("rhpds.widget") is None  # Only 2 parts
```

### End-to-End Integration Testing

**Tests Missing:**
- Full pipeline: pre_filter_jobs → orchestrator → store_report
- Malformed pre_filter output handling
- Batch processing at scale (100+ jobs)

```python
def test_end_to_end_pre_filter_to_store_report():
    # 1. Run pre_filter_jobs on batch of jobs
    # 2. Parse output (analyze_ids, pre_matched, dupes)
    # 3. Simulate orchestrator analysis
    # 4. Call store_report with results
    # 5. Verify final DB state: correct links, pattern_ids, dupes

def test_batch_processing_at_scale():
    # 100+ jobs in batch, 100+ historical results
    # Confirm no timeout, no performance issues
```

### Result Lookup and Null Handling

**Tests Missing:**
- Missing result rows in pattern validation
- NULL related_result_id transitions

```python
def test_post_analysis_link_handles_missing_pattern_member_row():
    # Pattern with jobs [1, 2, 3]
    # Result rows for 1 and 3 exist; row for 2 is missing
    # Confirm entire pattern is dropped (no partial links)
```

## Implementation Recommendations

**Priority 1 (Address Known Issues):**
1. Cyclic/chained `related_result_id` detection
2. Double-failed representative recovery state
3. Confidence erosion intentionality

**Priority 2 (Boundary Testing):**
1. Text similarity threshold boundaries
2. Generic token case folding
3. Ambiguous catalogs with 3+ categories

**Priority 3 (Integration & Scale):**
1. End-to-end pipeline testing
2. Large batch processing
3. Malformed input handling
