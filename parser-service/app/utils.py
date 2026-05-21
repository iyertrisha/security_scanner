"""Utility functions for file detection and content analysis"""
from typing import Tuple

def detect_file_type(filename: str, content: str) -> str:
    """Detect file type from filename and content"""
    filename_lower = filename.lower()
    
    if filename_lower.endswith(".tf"):
        return "terraform"
    elif filename_lower.endswith((".yaml", ".yml")):
        return "kubernetes"
    elif filename_lower.endswith(".json"):
        # Could be Kubernetes or other JSON
        if "apiVersion" in content or "kind" in content:
            return "kubernetes"
        return "json"
    elif filename_lower.endswith(".xml"):
        return "xml"
    
    # Content-based detection as fallback
    if "apiVersion" in content and "kind" in content:
        return "kubernetes"
    elif "resource" in content and "provider" in content:
        return "terraform"
    
    return "unknown"

def detect_provider(content: str) -> str:
    """Detect cloud provider from content"""
    content_lower = content.lower()
    
    # Terraform-specific providers
    if "aws_" in content_lower:
        return "aws"
    elif "google_" in content_lower or "gcp" in content_lower:
        return "gcp"
    elif "azurerm_" in content_lower:
        return "azure"
    elif "oci_" in content_lower:
        return "oracle"
    
    # Kubernetes - check for known patterns
    if "apiVersion" in content and "kind" in content:
        if "image:" in content or "containers:" in content:
            return "kubernetes"
    
    return "unknown"

def detect_file_and_provider(filename: str, content: str) -> Tuple[str, str]:
    """Detect both file type and provider"""
    file_type = detect_file_type(filename, content)
    provider = detect_provider(content)
    
    # If file type is terraform, ensure provider is detected
    if file_type == "terraform" and provider == "unknown":
        provider = "aws"  # Default to AWS for terraform
    
    # If file type is kubernetes, ensure provider is set
    if file_type == "kubernetes" and provider == "unknown":
        provider = "kubernetes"
    
    return file_type, provider
