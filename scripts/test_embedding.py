"""Throwaway script to test google-genai SDK with Vertex AI backend."""

from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project="raman-gcp-project-k8s-dev",
    location="us-central1",
)

response = client.models.embed_content(
    model="text-embedding-005",
    contents=["Metformin dosing in patients with renal impairment"],
    config=types.EmbedContentConfig(
        output_dimensionality=768,
        task_type="RETRIEVAL_DOCUMENT",
    ),
)

embedding = response.embeddings[0].values
print(f"Status: SUCCESS")
print(f"Dimensions: {len(embedding)}")
print(f"First 5 values: {embedding[:5]}")
