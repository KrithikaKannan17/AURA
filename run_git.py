import subprocess, os, sys

os.chdir("/Users/krithikakannan/Desktop/PROJECTSS/AURA")

def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(f"$ {cmd}")
    if result.stdout: print(result.stdout)
    if result.stderr: print(result.stderr)
    print()

run("git init")
run("git add README.md")
run('git commit -m "first commit"')
run("git branch -M main")
run("git remote add origin https://github.com/KrithikaKannan17/AURA.git")
run("git add .")
run('git commit -m "feat: initial AURA multi-agent RAG system"')
run("git push -u origin main")
