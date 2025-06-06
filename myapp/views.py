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
    file_names = [item['name'] for item in contents if 'name' in item]
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


def github_and_gemini(request):
    prompt = request.GET.get("prompt", "").strip()

    if not prompt:
        return JsonResponse({"error": "Prompt is required"}, status=400)

    # Enhance full user prompt intelligently (no keyword removal)
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

        # GitHub Query
        search_query = " ".join(enhanced_prompt.split())

        def search_github(query):
            response = requests.get(
                "https://api.github.com/search/repositories",
                headers={"Authorization": f"token {GITHUB_TOKEN}"},
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 5},
                timeout=10
            )
            return response.json().get("items", [])[:5]

        # Primary Search
        repos = search_github(search_query)

        # Fallback if no results
        if not repos:
            fallback_query = "+".join(prompt.split())
            print("Fallback GitHub Query:", fallback_query)
            repos = search_github(fallback_query)

        filtered_repos = []

        for repo in repos:
            owner = repo["owner"]["login"]
            repo_name = repo["name"]
            description = repo.get("description", "") or ""

            # Repo Structure for Level Detection
            contents_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents"
            contents_res = requests.get(contents_url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=10)
            contents = contents_res.json() if contents_res.status_code == 200 else []
            level = get_level_by_structure(contents)

            # Try to fetch README
            readme_url = f"https://api.github.com/repos/{owner}/{repo_name}/readme"
            readme_res = requests.get(readme_url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=10)

            if readme_res.status_code == 200:
                content = readme_res.json().get("content", "")
                decoded = base64.b64decode(content).decode("utf-8", errors="ignore")
                summary_prompt = f"Summarize the following GitHub README:\n\n{decoded}"
            else:
                # Try fetching key code files if README is missing
                key_files = [f for f in contents if f.get("name") in ["main.py", "app.js", "index.js", "server.js"]]
                code_snippets = ""

                for file in key_files:
                    code_res = requests.get(file["download_url"])
                    if code_res.status_code == 200:
                        snippet = code_res.text[:1000]
                        code_snippets += f"\n\n# {file['name']}:\n{snippet}"

                if code_snippets:
                    summary_prompt = f"Summarize this GitHub project based on these code files:\n{code_snippets}"
                else:
                    summary_prompt = "This project has no README and no key files could be fetched."

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

        return JsonResponse({
            "original_prompt": prompt,
            "enhanced_prompt": enhanced_prompt,
            "repositories": filtered_repos
        }, status=200)

    except Exception as e:
        print("ERROR:", str(e))
        return JsonResponse({"error": str(e)}, status=500)