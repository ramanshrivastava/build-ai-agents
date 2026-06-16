"""Standalone FastMCP server exposing the clinical guideline search tool over HTTP.

This package runs as its own process and serves the same `search_clinical_guidelines`
capability the in-process SDK MCP server provides, but over Streamable HTTP — simulating
a third-party-hosted MCP server the briefing agent connects to remotely.
"""
