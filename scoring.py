"""
University scoring and categorization logic.
"""

from typing import List, Dict, Tuple
from models import CategoryEnum

def score_university(
    gpa: float,
    budget: int,
    university: Dict
) -> float:
    """
    Score a university based on user profile fit.
    
    Args:
        gpa: User's GPA (0-10 scale)
        budget: User's annual budget in USD
        university: University dict with rank, estimated_tuition_usd, competitiveness
    
    Returns:
        Score from 0-100 (higher is better fit)
    """
    score = 0.0
    
    # Rank score (40 points max)
    # Lower rank = better university, but may be harder to get into
    rank = university.get("rank", 500)
    if rank <= 50:
        rank_score = 40
    elif rank <= 100:
        rank_score = 35
    elif rank <= 200:
        rank_score = 30
    elif rank <= 300:
        rank_score = 25
    else:
        rank_score = 20
    score += rank_score
    
    # Budget fit score (30 points max)
    tuition = university.get("estimated_tuition_usd", 0)
    if tuition <= budget * 0.7:
        # Well within budget
        budget_score = 30
    elif tuition <= budget:
        # Within budget
        budget_score = 25
    elif tuition <= budget * 1.2:
        # Slightly over budget
        budget_score = 15
    else:
        # Too expensive
        budget_score = 5
    score += budget_score
    
    # GPA vs competitiveness match (30 points max)
    competitiveness = university.get("competitiveness", "MEDIUM")
    if competitiveness == "HIGH":
        # Need high GPA for high competitiveness
        if gpa >= 8.5:
            gpa_score = 30
        elif gpa >= 7.5:
            gpa_score = 20
        else:
            gpa_score = 10
    elif competitiveness == "MEDIUM":
        # Medium GPA acceptable
        if gpa >= 7.0:
            gpa_score = 30
        elif gpa >= 6.0:
            gpa_score = 25
        else:
            gpa_score = 15
    else:  # LOW or VERY_LOW
        # Lower GPA acceptable
        if gpa >= 6.0:
            gpa_score = 30
        else:
            gpa_score = 25
    score += gpa_score
    
    return score

def categorize_universities(
    universities: List[Dict],
    gpa: float,
    budget: int
) -> Dict[str, List[Dict]]:
    """
    Categorize universities into DREAM, TARGET, SAFE.
    
    Args:
        universities: List of university dicts
        gpa: User's GPA
        budget: User's budget
    
    Returns:
        Dict with keys: dream, target, safe
    """
    # Score all universities
    scored = []
    for uni in universities:
        score = score_university(gpa, budget, uni)
        scored.append((uni, score))
    
    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    
    categorized = {
        "dream": [],
        "target": [],
        "safe": []
    }
    
    # Categorize based on rank and competitiveness
    # Categorize based on rank and competitiveness
    for uni, score in scored:
        ranking_rank = uni.get("rank", 500)
        competitiveness = uni.get("competitiveness", "MEDIUM")
        
        # Inject match percentage
        uni["match_percentage"] = int(score)
        
        # Determine Category
        category = "TARGET" # Default
        
        # DREAM: Top ranked, highly competitive
        if ranking_rank <= 50 and competitiveness == "HIGH":
            category = "DREAM"
        
        # SAFE: Lower ranked, less competitive
        elif ranking_rank > 100 or competitiveness in ["LOW", "VERY_LOW"]:
            category = "SAFE"
            
        # TARGET: Mid-tier
        elif ranking_rank <= 100 and competitiveness in ["HIGH", "MEDIUM"]:
            category = "TARGET"
            
        uni["category"] = category
        
        # Add to respective list (Max 5 per category)
        target_list = categorized[category.lower()]
        if len(target_list) < 5:
            target_list.append(uni)
        # Fallback distribution if full? 
        # For simplicity, we stick to strict limits to ensure quality recommendations
    
    return categorized
