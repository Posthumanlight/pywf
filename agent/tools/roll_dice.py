import numpy as np
from typing import Literal
from langchain.tools import tool

@tool
def roll_dice(count: int, d: int, mode: Literal["normal", "advantage", "disadvantage"] = "normal") -> str:
    '''Roll dice for the character. Call ONLY when the DM has asked for a roll
    or the table convention allows it. Never state a roll result yourself;
    results come only from this tool.

    Args:
        count: number of dice (e.g. 2 for 2d6)
        d: faces per die (4, 6, 8, 10, 12, 20, 100)
        mode: advantage/disadvantage means rolling twice and selecting higher or lower value respectively
    '''
    results = []
    match mode:
        case "normal":
            for i in range(count):
                results.append(np.random.randint(1,d+1))
        case "advantage":
            for i in range(count):
                results.append(max(np.random.randint(1,d+1), np.random.randint(1,d+1)))
        case "disadvantage":
            for i in range(count):
                results.append(min(np.random.randint(1,d+1), np.random.randint(1,d+1)))

    return (f"Rolls for {count}d{d}: {results}")