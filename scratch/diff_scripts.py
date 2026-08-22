import os
import filecmp

local_dir = r"c:\Dev\JobAgentApply\scripts"
remote_dir = r"L:\My Drive\Work\Code\JobApply"

def compare_dirs(dir1, dir2):
    dcmp = filecmp.dircmp(dir1, dir2)
    
    output = []
    output.append("=== FILES ONLY IN LOCAL ===")
    for f in dcmp.left_only:
        output.append(f)
        
    output.append("\n=== FILES ONLY IN REMOTE ===")
    for f in dcmp.right_only:
        output.append(f)
        
    output.append("\n=== FILES THAT DIFFER ===")
    for f in dcmp.diff_files:
        path1 = os.path.join(dir1, f)
        path2 = os.path.join(dir2, f)
        size1 = os.path.getsize(path1)
        size2 = os.path.getsize(path2)
        output.append(f"{f}: Local ({size1} bytes) | Remote ({size2} bytes)")
        
    with open(r"c:\Dev\AiVoiceTagger\scratch\diff_output.txt", "w", encoding="utf-8") as out:
        out.write("\n".join(output))

compare_dirs(local_dir, remote_dir)
