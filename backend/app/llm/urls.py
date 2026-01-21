from django.urls import path

from .views import OllamaChatView
from .views import OllamaModelsView

urlpatterns = [
    path("chat", OllamaChatView.as_view(), name="ollama-chat"),
    path("models", OllamaModelsView.as_view(), name="ollama-models"),
]

