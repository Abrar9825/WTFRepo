from django.shortcuts import render
from django.http import JsonResponse
import google.generativeai as genai
from dotenv import load_dotenv
import requests
import os
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

    promptforgenrate = "AI timetable generator in machine learning, data science, and AI"
    #promptforgenrate = request.GET.get("prompt", ...)
    prompt = request.GET.get("prompt", f"{promptforgenrate} short and concise keywords to find repos easily")  # Default prompt if none provided
    try:
        # Call Google Gemini to enhance the prompt
        model = genai.GenerativeModel('gemini-1.5-flash')
        enhanced_prompt = model.generate_content(prompt).text.strip()

        # Clean up the enhanced prompt
        keywords = enhanced_prompt.split()[:4]  # Use only up to 4 keywords
        clean_prompt = " ".join(keywords)

        # Call GitHub API with the cleaned prompt
        github_response = requests.get(
            "https://api.github.com/search/repositories",
            headers={"Authorization": f"token {GITHUB_TOKEN}"},
            params={"q": clean_prompt, 
                    "language": "Python", 
                    "sort": "stars"}
        )
        repos=github_response.json().get("items",[])[:5]
        filtered_repos=[
            {
                "name":repo["name"],
                "description": " ".join(repo["description"].split()[:8]) ,
                "url":repo["html_url"],
                "stars":repo["stargazers_count"],
                "created_at":repo["created_at"]
            }
            for repo in repos
        ]

        # Return both Gemini and GitHub responses
        return JsonResponse({
            "enhanced_prompt": enhanced_prompt,
            "cleaned_prompt": clean_prompt,
            "repositories":filtered_repos
        }, status=github_response.status_code)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)