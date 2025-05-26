from django.shortcuts import render
from django.http import JsonResponse
import google.generativeai as genai
from dotenv import load_dotenv
import requests
import os
import base64
from django.conf import settings


# Load environment variables from .env file
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
genai.configure(api_key=GEMINI_API_KEY)

# Create your views here.
def index(request):
    return render(request, 'index.html')

def github_and_gemini(request):
    promptforgenrate = request.GET.get("prompt", ...)
    prompt = request.GET.get("prompt", f"{promptforgenrate} generate short keywords to find repos easily")

    try:
        # Call Gemini to enhance the prompt
        model = genai.GenerativeModel('gemini-1.5-flash')
        enhanced_prompt = model.generate_content(prompt).text.strip()

        keywords = enhanced_prompt.split()[:4]
        clean_prompt = " ".join(keywords)

        # GitHub API call
        github_response = requests.get(
            "https://api.github.com/search/repositories",
            headers={"Authorization": f"token {GITHUB_TOKEN}"},
            params={"q": clean_prompt, "sort": "stars"}
        )

        if github_response.status_code != 200:
            return JsonResponse({
                "error": "GitHub API error",
                "details": github_response.json()
            }, status=github_response.status_code)

        repos = github_response.json().get("items", [])[:5]
        filtered_repos = []

        for repo in repos:
            owner = repo["owner"]["login"]
            repo_name = repo["name"]

            # Try to get README
            readme_url = f"https://api.github.com/repos/{owner}/{repo_name}/readme"
            readme_res = requests.get(readme_url, headers={"Authorization": f"token {GITHUB_TOKEN}"})

            if readme_res.status_code == 200:
                readme_content = readme_res.json().get("content", "")
                summary_input = base64.b64decode(readme_content).decode("utf-8")
                summary_prompt = f"Summarize the following GitHub README:\n\n{summary_input}"
            else:
                # Try to get important code files
                contents_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents"
                contents_res = requests.get(contents_url, headers={"Authorization": f"token {GITHUB_TOKEN}"})

                summary_input = "Important files:\n"
                if contents_res.status_code == 200:
                    files = contents_res.json()
                    important_files = [f for f in files if f["name"] in ["app.js", "server.js", "main.py", "index.js"]]

                    for file in important_files:
                        file_res = requests.get(file["download_url"])
                        if file_res.status_code == 200:
                            file_content = file_res.text[:1000]  # Trim for safety
                            summary_input += f"\n\n# {file['name']}:\n{file_content}"

                    summary_prompt = f"Summarize this project based on these files:\n{summary_input}"
                else:
                    summary_prompt = "This project has no README and its file structure could not be retrieved."

            # Ask Gemini to summarize
            gemini_summary = model.generate_content(summary_prompt).text.strip()

            filtered_repos.append({
                "name": repo["name"],
                "description": " ".join(repo["description"].split()[:8]) if repo["description"] else "",
                "url": repo["html_url"],
                "stars": repo["stargazers_count"],
                "created_at": repo["created_at"],
                "summary": gemini_summary
            })

        return JsonResponse({
            "enhanced_prompt": enhanced_prompt,
            "cleaned_prompt": clean_prompt,
            "repositories": filtered_repos
        }, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


