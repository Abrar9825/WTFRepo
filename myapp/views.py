from django.shortcuts import render
from django.http import JsonResponse
import google.generativeai as genai
from dotenv import load_dotenv
import requests
import os
import base64

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
genai.configure(api_key=GEMINI_API_KEY)

def index(request):
    return render(request, 'index.html')

def get_level_by_structure(contents):
    file_names = [item['name'] for item in contents]
    dirs = [item['name'] for item in contents if item['type'] == 'dir']
    files = [item['name'] for item in contents if item['type'] == 'file']

    if len(files) <= 2 and not dirs:
        return "Beginner"
    elif "manage.py" in files or "app.py" in files or "main.py" in files:
        return "Intermediate" if len(dirs) <= 2 else "Advanced"
    elif len(dirs) >= 3 or ("requirements.txt" in files and "setup.py" in files):
        return "Advanced"
    return "Intermediate"

def github_and_gemini(request):
    user_query = request.GET.get("prompt", "").strip()
    try:
        # Gemini prompt processing
        gemini_prompt = f"Extract up to 3 search keywords from: '{user_query}'. Only space-separated keywords."
        model = genai.GenerativeModel('gemini-1.5-flash')
        keywords = model.generate_content(gemini_prompt).text.strip().split()[:3]
        
        # Build search query
        search_query = " ".join(keywords) + " language:python" if keywords else f"{user_query} language:python"
        
        # GitHub API call
        github_params = {"q": search_query, "sort": "stars", "order": "desc", "per_page": 5}
        repos = requests.get(
            "https://api.github.com/search/repositories",
            headers={"Authorization": f"token {GITHUB_TOKEN}"},
            params=github_params,
            timeout=10
        ).json().get("items", [])

        # Fallback search if insufficient results
        if len(repos) < 5:
            fallback_repos = requests.get(
                "https://api.github.com/search/repositories",
                headers={"Authorization": f"token {GITHUB_TOKEN}"},
                params={"q": f"{user_query} language:python", "sort": "stars", "per_page": 5},
                timeout=10
            ).json().get("items", [])
            repos = list({r['html_url']: r for r in repos + fallback_repos}.values())[:5]

        # Process repositories
        filtered_repos = []
        for repo in repos[:5]:
            owner = repo["owner"]["login"]
            name = repo["name"]
            
            # Get repository contents
            contents_resp = requests.get(
                f"https://api.github.com/repos/{owner}/{name}/contents",
                headers={"Authorization": f"token {GITHUB_TOKEN}"},
                timeout=10
            )
            contents = contents_resp.json() if contents_resp.status_code == 200 else []
            level = get_level_by_structure(contents) if contents else "Unknown"
            
            # Get README or generate summary
            readme_resp = requests.get(
                f"https://api.github.com/repos/{owner}/{name}/readme",
                headers={"Authorization": f"token {GITHUB_TOKEN}"},
                timeout=10
            )
            if readme_resp.status_code == 200:
                summary = base64.b64decode(readme_resp.json()['content']).decode('utf-8')[:2000]
            else:
                language = repo.get('language', 'Unknown')
                files = [item['name'] for item in contents][:10]
                summary = f"Language: {language}\nMain files: {', '.join(files)}"

            filtered_repos.append({
                "name": repo.get("name", "Unknown"),
                "description": " ".join((repo.get("description") or "").split()[:12]),
                "url": repo.get("html_url", "#"),
                "stars": repo.get("stargazers_count", 0),
                "created_at": repo.get("created_at", "")[:10],
                "level": level,
                "summary": summary
            })

        return JsonResponse({
            "original_query": user_query,
            "gemini_keywords": keywords,
            "search_query": search_query,
            "repositories": filtered_repos
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
