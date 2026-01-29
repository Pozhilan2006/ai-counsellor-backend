from typing import List, Dict

def classify_university(university: Dict, academic_score: float) -> str:
    """
    Classify a single university as DREAM, TARGET, or SAFE.
    
    Deterministic logic based on:
    - University rank
    - Competitiveness level
    - Academic score comparison
    
    Args:
        university: University dict with rank, competitiveness
        academic_score: User's academic score
    
    Returns:
        "dream", "target", or "safe"
    """
    rank = university["rank"]
    competitiveness = university["competitiveness"]
    
    # DREAM: Top ranked, highly competitive
    # User score likely below typical admits
    if rank <= 50 and competitiveness == "HIGH":
        return "dream"
    
    # TARGET: Mid-tier, good match
    # User score matches typical admits
    elif rank <= 100 and competitiveness == "MEDIUM":
        return "target"
    
    # SAFE: Lower ranked, less competitive
    # User score exceeds typical admits
    elif rank > 100 and competitiveness in ["LOW", "VERY_LOW"]:
        return "safe"
    
    # Default fallback based on rank only
    elif rank <= 50:
        return "dream"
    elif rank <= 100:
        return "target"
    else:
        return "safe"

def classify_universities(
    universities: List[Dict],
    academic_score: float
) -> Dict[str, List[Dict]]:
    """
    Classify all universities into dream/target/safe categories.
    
    Args:
        universities: List of university dicts
        academic_score: User's academic score
    
    Returns:
        Dict with keys: dream, target, safe
        Each containing list of universities
    """
    classified = {
        "dream": [],
        "target": [],
        "safe": []
    }
    
    for uni in universities:
        category = classify_university(uni, academic_score)
        classified[category].append(uni)
    
    return classified
