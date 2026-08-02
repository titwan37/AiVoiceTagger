# 1. Initialize Git repository (if not already done)
git init

# 2. Stage all project files
git add .

# 3. Create initial commit
git commit -m "feat: initial commit for AiVoiceTagger Rust core & Python NLP sidecar"

# 4. Set main branch name
git branch -M main

# 5. Add remote GitHub repository
git remote add origin https://github.com/titwan37/AiVoiceTagger.git

# 6. Push to GitHub
git push -u origin main
