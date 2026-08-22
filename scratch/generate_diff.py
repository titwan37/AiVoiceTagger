import os
import difflib

local_dir = r"c:\Dev\JobAgentApply\scripts"
remote_dir = r"L:\My Drive\Work\Code\JobApply"

files_to_diff = [
    "Qwen3_CareerCoach_Dual.py",
    "compile_xelatex.py",
    "JobHistory_WizardManager.py",
    "Jobapply_QuickMatcher_Faiss_v2.py",
    "fileUtils.py",
    "profiler.py",
    "response_formatting.py",
    "JobApply_MasterMenu.py"
]

output = []

for f in files_to_diff:
    path1 = os.path.join(local_dir, f)
    path2 = os.path.join(remote_dir, f)
    
    if os.path.exists(path1) and os.path.exists(path2):
        with open(path1, "r", encoding="utf-8", errors="ignore") as file1:
            lines1 = file1.readlines()
        with open(path2, "r", encoding="utf-8", errors="ignore") as file2:
            lines2 = file2.readlines()
            
        diff = list(difflib.unified_diff(
            lines1, lines2, 
            fromfile=f'LOCAL: {f}', 
            tofile=f'REMOTE: {f}', 
            n=2
        ))
        
        output.append(f"====== DIFF FOR {f} ======")
        if not diff:
            output.append("No differences found.")
        else:
            # We'll just take the first 100 lines of diff for each to keep it manageable
            output.append("".join(diff[:100]))
            if len(diff) > 100:
                output.append(f"... (truncated {len(diff)-100} lines of diff)")
        output.append("\n")

with open(r"c:\Dev\AiVoiceTagger\scratch\detailed_diffs.txt", "w", encoding="utf-8") as out:
    out.write("\n".join(output))
