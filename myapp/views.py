from django.shortcuts import render
from django.http import JsonResponse
import google.generativeai as genai
from dotenv import load_dotenv
import requests
import os
import base64

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

def index(request):
    return render(request, 'index.html')

def get_level_by_structure(contents):
    if not contents or not isinstance(contents, list):
        return "Unknown"
    dirs = [item['name'] for item in contents if item.get('type') == 'dir']
    files = [item['name'] for item in contents if item.get('type') == 'file']

    if len(files) <= 2 and not dirs:
        return "Beginner"
    elif "manage.py" in files or "app.py" in files or "main.py" in files:
        return "Intermediate" if len(dirs) <= 2 else "Advanced"
    elif len(dirs) >= 3 or ("requirements.txt" in files and "setup.py" in files):
        return "Advanced"
    return "Intermediate"

def full_summary_view(request):
    summary = request.GET.get('summary', 'No summary provided.')
    return render(request, 'full_summary.html', {'summary': summary})

def search_github(query, sort="stars"):
    response = requests.get(
        "https://api.github.com/search/repositories",
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        params={"q": query, "sort": sort, "order": "desc", "per_page": 5},
        timeout=10
    )
    return response.json().get("items", [])[:5]

def github_and_gemini(request):
    prompt = request.GET.get("prompt", "").strip()
    if not prompt:
        return JsonResponse({"error": "Prompt is required"}, status=400)

    gemini_prompt = (
        f"Rewrite and enhance the following user search query to be optimized for GitHub repository search. "
        f"Focus on adding relevant programming languages, frameworks, and keywords related to the project idea. "
        f"Use GitHub search syntax where possible, like language:python or topic:machine-learning. "
        f"Return only a single line of text, no markdown, no explanation:\n\n{prompt}"
    )

    try:
        enhanced_prompt = model.generate_content(gemini_prompt).text.strip()
        print("Original Prompt:", prompt)
        print("Gemini Enhanced:", enhanced_prompt)

        # Try enhanced prompt
        repos = search_github(" ".join(enhanced_prompt.split()))

        # Fallback 1: Try raw prompt
        if not repos:
            fallback_query = "+".join(prompt.split())
            print("Fallback GitHub Query:", fallback_query)
            repos = search_github(fallback_query)

        # Fallback 2: Relaxed search (remove language/topic, use only main keywords)
        if not repos:
            keywords = " ".join(prompt.split()[:3])  # Use first 3 words as broad keywords
            print("Relaxed keywords search:", keywords)
            repos = search_github(keywords, sort="best-match")

        # Fallback 3: Even broader (only one keyword)
        if (not repos) and prompt:
            main_word = prompt.split()[0]
            print("Broadest search using:", main_word)
            repos = search_github(main_word, sort="best-match")

        filtered_repos = []
        for repo in repos:
            owner = repo["owner"]["login"]
            repo_name = repo["name"]
            description = repo.get("description", "") or ""

            # Get repo structure
            contents_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents"
            contents_res = requests.get(contents_url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=10)
            contents = contents_res.json() if contents_res.status_code == 200 else []
            level = get_level_by_structure(contents)

            # Always fetch README if present
            readme_text = ""
            readme_url = f"https://api.github.com/repos/{owner}/{repo_name}/readme"
            readme_res = requests.get(readme_url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=10)
            if readme_res.status_code == 200:
                content = readme_res.json().get("content", "")
                readme_text = base64.b64decode(content).decode("utf-8", errors="ignore")

            # Always fetch key files (even if README exists)
            file_prompts = []
            for item in contents:
                if item.get("type") == "file":
                    file_name = item.get("name")
                    if any(file_name.lower().endswith(ext) for ext in [".py", ".js", ".md", ".txt", ".json", ".yaml", ".yml"]):
                        code_res = requests.get(item["download_url"])
                        if code_res.status_code == 200:
                            file_content = code_res.text
                            file_prompts.append(f"## {file_name}\n{file_content[:2000]}")
            file_prompts = file_prompts[:10]

            # Build combined prompt for Gemini
            summary_prompt = (
                "You are summarizing a GitHub project for a user who needs a detailed, bullet-point breakdown. "
                "Your summary MUST include:\n"
                "- Project purpose (in 1-2 lines)\n"
                "- Point-by-point (bullet list) of ALL important files in the project (with what each does)\n"
                "- Point-by-point (bullet list) of key features and functions\n"
                "- Step-by-step instructions on how to set up and run the project\n"
                "- A clear explanation of the code structure and flow (entry point, main logic, etc.)\n\n"
            )
            if readme_text:
                summary_prompt += "README:\n" + readme_text + "\n\n"
            if file_prompts:
                summary_prompt += (
                    "Below are the key files from the project:\n\n"
                    + "\n\n".join(file_prompts)
                    + "\n\n"
                )
            summary_prompt += (
                "Summarize this project as requested above, using bullet points for lists. Make it easy for a new user to understand."
            )

            try:
                gemini_summary = model.generate_content(summary_prompt).text.strip()
            except Exception as e:
                gemini_summary = "Summary generation failed."

            filtered_repos.append({
                "name": repo_name,
                "description": " ".join(description.split()[:12]),
                "url": repo["html_url"],
                "stars": repo["stargazers_count"],
                "created_at": repo["created_at"][:10],
                "level": level,
                "summary": gemini_summary
            })

        result_type = "exact" if filtered_repos else "closest"
        return JsonResponse({
            "original_prompt": prompt,
            "enhanced_prompt": enhanced_prompt,
            "result_type": result_type,  # Indicate if these are "closest matches"
            "repositories": filtered_repos
        }, status=200)

    except Exception as e:
        print("ERROR:", str(e))
        return JsonResponse({"error": str(e)}, status=500)