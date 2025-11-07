"""
FastAPI Market Analysis Agent
Dynamic API for social media campaign planning with real-time research

Install dependencies:
pip install fastapi uvicorn openai exa-py agno firecrawl python-dotenv pydantic groq python-multipart
"""

from datetime import datetime, timedelta
from textwrap import dedent
from typing import Optional, List, Dict, Any, Union
import os
import asyncio
import json
import re
import time
import hashlib
import csv
import smtplib
import io
from contextlib import asynccontextmanager
from email.mime.text import MIMEText
from groq import Groq

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from agno.agent import Agent
from agno.models.google import Gemini
from agno.tools.exa import ExaTools
from agno.tools.firecrawl import FirecrawlTools
from dotenv import load_dotenv
from image import visual_asset_manager
from audience_intelligence_analyzer import (
    AudienceIntelligenceRequest, 
    AudienceIntelligenceResponse,
    analyze_audience_intelligence
)
from copy_content_generator import generate_social_content
from campaign_timeline_optimizer import (
    CampaignTimelineRequest,
    CampaignTimelineResponse,
    optimize_campaign_timeline
)
from content_distribution_scheduler import (
    ContentDistributionRequest,
    ContentDistributionResponse,
    schedule_content_distribution
)
from email_sender import (
    EmailCampaignRequest,
    EmailCampaignResponse,
    EmailRecipient,
    send_email_campaign
)

# Try to import SendGrid version if available
try:
    from email_sender_sendgrid import send_email_campaign_sendgrid
    SENDGRID_AVAILABLE = True
    print("✅ SendGrid email sender available")
except ImportError:
    SENDGRID_AVAILABLE = False
    print("⚠️ SendGrid not installed, using SMTP fallback")

# Load environment variables
load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")
os.environ["EXA_API_KEY"] = os.getenv("EXA_API_KEY")

# Global agent instance
agent = None

# Cache for API responses to reduce rate limiting
response_cache: Dict[str, Dict[str, Any]] = {}
CACHE_DURATION = 3600  # 1 hour cache

# Rate limit tracking
rate_limit_tracker = {
    "exa_last_reset": 0,
    "firecrawl_last_reset": 0,
    "exa_requests_count": 0,
    "firecrawl_requests_count": 0
}

def get_cache_key(prompt: str) -> str:
    """Generate cache key for prompt"""
    return hashlib.md5(prompt.encode()).hexdigest()

def is_cache_valid(cache_entry: Dict[str, Any]) -> bool:
    """Check if cache entry is still valid"""
    if not cache_entry:
        return False
    cache_time = cache_entry.get("timestamp", 0)
    return time.time() - cache_time < CACHE_DURATION

async def retry_with_backoff(func, max_retries: int = 3, base_delay: float = 1.0):
    """Retry function with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return await func() if asyncio.iscoroutinefunction(func) else func()
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"Rate limited, retrying in {delay} seconds... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue
            raise e
    raise Exception("Max retries exceeded")

def check_rate_limits() -> Dict[str, bool]:
    """Check if we're within rate limits"""
    current_time = time.time()
    
    # Reset counters every hour
    if current_time - rate_limit_tracker["exa_last_reset"] > 3600:
        rate_limit_tracker["exa_requests_count"] = 0
        rate_limit_tracker["exa_last_reset"] = current_time
    
    if current_time - rate_limit_tracker["firecrawl_last_reset"] > 3600:
        rate_limit_tracker["firecrawl_requests_count"] = 0
        rate_limit_tracker["firecrawl_last_reset"] = current_time
    
    # Conservative limits (adjust based on your API quotas)
    exa_limit = 50  # requests per hour
    firecrawl_limit = 100  # requests per hour
    
    return {
        "exa_available": rate_limit_tracker["exa_requests_count"] < exa_limit,
        "firecrawl_available": rate_limit_tracker["firecrawl_requests_count"] < firecrawl_limit
    }

def calculate_start_date(days: int) -> str:
    """Calculate start date based on number of days."""
    start_date = datetime.now() - timedelta(days=days)
    return start_date.strftime("%Y-%m-%d")

# Pydantic Models for Module Configurations
class BrandGuidelines(BaseModel):
    colors: Optional[List[str]] = Field(None, description="Brand colors")
    style: Optional[str] = Field(None, description="Visual style")
    logo_url: Optional[str] = Field(None, description="Logo URL")

class Dimensions(BaseModel):
    width: Optional[int] = Field(None, description="Width in pixels")
    height: Optional[int] = Field(None, description="Height in pixels")

class BackgroundMusic(BaseModel):
    music_style: Optional[str] = Field(None, description="Music style")
    volume: Optional[float] = Field(None, description="Volume level")

class Voiceover(BaseModel):
    voice_type: Optional[str] = Field(None, description="Voice type")
    language: Optional[str] = Field(None, description="Language")

class TargetAudience(BaseModel):
    product_description: Optional[str] = Field(None, description="Product description")
    demographics: Optional[str] = Field(None, description="Demographics")
    psychographics: Optional[str] = Field(None, description="Psychographics")
    pain_points: Optional[List[str]] = Field(None, description="Pain points")

class WordCountRange(BaseModel):
    min: Optional[int] = Field(None, description="Minimum word count")
    max: Optional[int] = Field(None, description="Maximum word count")

class GeographicLocation(BaseModel):
    country: Optional[str] = Field(None, description="Country")
    city: Optional[str] = Field(None, description="City")
    region: Optional[str] = Field(None, description="Region")

class ExistingCustomerData(BaseModel):
    age_range: Optional[str] = Field(None, description="Age range")
    interests: Optional[List[str]] = Field(None, description="Interests")
    behavior_patterns: Optional[List[str]] = Field(None, description="Behavior patterns")

class CampaignDuration(BaseModel):
    start_date: Optional[str] = Field(None, description="Start date")
    end_date: Optional[str] = Field(None, description="End date")

class ContentInventory(BaseModel):
    content_id: Optional[str] = Field(None, description="Content ID")
    content_type: Optional[str] = Field(None, description="Content type")
    platform: Optional[str] = Field(None, description="Platform")

class OptimalPostingTimes(BaseModel):
    platform: Optional[str] = Field(None, description="Platform")
    time_slots: Optional[List[str]] = Field(None, description="Time slots")

class PostingFrequency(BaseModel):
    min_posts_per_day: Optional[int] = Field(None, description="Minimum posts per day")
    max_posts_per_day: Optional[int] = Field(None, description="Maximum posts per day")

class KeyDate(BaseModel):
    date: Optional[str] = Field(None, description="Date")
    event: Optional[str] = Field(None, description="Event")
    priority: Optional[List[str]] = Field(None, description="Priority level")

class TimelineSlot(BaseModel):
    timeline_slot_id: Optional[str] = Field(None, description="Timeline slot ID")
    scheduled_date: Optional[str] = Field(None, description="Scheduled date")
    content_type: Optional[str] = Field(None, description="Content type")
    platform: Optional[str] = Field(None, description="Platform")
    target_segment: Optional[str] = Field(None, description="Target segment")
    priority: Optional[List[str]] = Field(None, description="Priority")

class GeneratedCopy(BaseModel):
    copy_text: Optional[str] = Field(None, description="Copy text")
    copy_id: Optional[str] = Field(None, description="Copy ID")
    word_count: Optional[int] = Field(None, description="Word count")
    hashtags: Optional[List[str]] = Field(None, description="Hashtags")
    emojis: Optional[List[str]] = Field(None, description="Emojis")

class GeneratedImage(BaseModel):
    image_url: Optional[str] = Field(None, description="Image URL")
    image_id: Optional[str] = Field(None, description="Image ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata")

class PlatformSpecifications(BaseModel):
    platform_name: Optional[str] = Field(None, description="Platform name")
    max_caption_length: Optional[int] = Field(None, description="Max caption length")
    supported_formats: Optional[List[str]] = Field(None, description="Supported formats")
    aspect_ratio_requirements: Optional[str] = Field(None, description="Aspect ratio requirements")

class ContentPackage(BaseModel):
    copy_id: Optional[str] = Field(None, description="Copy ID")
    copy_text: Optional[str] = Field(None, description="Copy text")
    asset_ids: Optional[List[str]] = Field(None, description="Asset IDs")
    asset_urls: Optional[List[str]] = Field(None, description="Asset URLs")

class PostingParameters(BaseModel):
    hashtags: Optional[List[str]] = Field(None, description="Hashtags")
    mentions: Optional[List[str]] = Field(None, description="Mentions")
    location_tag: Optional[str] = Field(None, description="Location tag")

class ScheduleItem(BaseModel):
    schedule_item_id: Optional[str] = Field(None, description="Schedule item ID")
    scheduled_datetime: Optional[str] = Field(None, description="Scheduled datetime")
    platform: Optional[str] = Field(None, description="Platform")
    content_package: Optional[ContentPackage] = Field(None, description="Content package")
    posting_parameters: Optional[PostingParameters] = Field(None, description="Posting parameters")
    target_segment: Optional[str] = Field(None, description="Target segment")

class PlatformCredentials(BaseModel):
    platform_name: Optional[str] = Field(None, description="Platform name")
    auth_token: Optional[str] = Field(None, description="Auth token")
    account_id: Optional[str] = Field(None, description="Account ID")

class ContactInfo(BaseModel):
    name: Optional[str] = Field(None, description="Name")
    email: Optional[str] = Field(None, description="Email")
    phone: Optional[str] = Field(None, description="Phone")
    company: Optional[str] = Field(None, description="Company")
    job_title: Optional[str] = Field(None, description="Job title")
    linkedin_url: Optional[str] = Field(None, description="LinkedIn URL")

class DiscoveredLead(BaseModel):
    lead_id: Optional[str] = Field(None, description="Lead ID")
    contact_info: Optional[ContactInfo] = Field(None, description="Contact info")

class CallWindowPreferences(BaseModel):
    timezone: Optional[str] = Field(None, description="Timezone")
    preferred_hours: Optional[List[str]] = Field(None, description="Preferred hours")
    avoid_dates: Optional[List[str]] = Field(None, description="Avoid dates")

class PrioritizationCriteria(BaseModel):
    qualification_score_threshold: Optional[float] = Field(None, description="Qualification score threshold")
    priority_segments: Optional[List[str]] = Field(None, description="Priority segments")

class CallSchedule(BaseModel):
    schedule_id: Optional[str] = Field(None, description="Schedule ID")
    lead_id: Optional[str] = Field(None, description="Lead ID")
    scheduled_datetime: Optional[str] = Field(None, description="Scheduled datetime")
    call_objective: Optional[List[str]] = Field(None, description="Call objective")

class CallScript(BaseModel):
    opening: Optional[str] = Field(None, description="Opening")
    talking_points: Optional[List[str]] = Field(None, description="Talking points")
    objection_handling: Optional[Dict[str, Any]] = Field(None, description="Objection handling")
    closing: Optional[str] = Field(None, description="Closing")
    follow_up: Optional[List[str]] = Field(None, description="Follow up")

class VoiceSettings(BaseModel):
    voice_type: Optional[str] = Field(None, description="Voice type")
    speech_rate: Optional[float] = Field(None, description="Speech rate")
    language: Optional[str] = Field(None, description="Language")

class SearchCriteria(BaseModel):
    industry: Optional[List[str]] = Field(None, description="Industry")
    company_size: Optional[str] = Field(None, description="Company size")
    job_titles: Optional[List[str]] = Field(None, description="Job titles")
    location: Optional[str] = Field(None, description="Location")

class QualificationCriteria(BaseModel):
    budget_range: Optional[str] = Field(None, description="Budget range")
    decision_making_authority: Optional[bool] = Field(None, description="Decision making authority")
    timeline: Optional[str] = Field(None, description="Timeline")

class TargetProfile(BaseModel):
    profile_id: Optional[str] = Field(None, description="Profile ID")
    platform: Optional[str] = Field(None, description="Platform")
    profile_url: Optional[str] = Field(None, description="Profile URL")
    audience_size: Optional[int] = Field(None, description="Audience size")
    engagement_rate: Optional[float] = Field(None, description="Engagement rate")
    content_categories: Optional[List[str]] = Field(None, description="Content categories")

class TemplateGuidelines(BaseModel):
    max_length: Optional[int] = Field(None, description="Max length")
    tone: Optional[str] = Field(None, description="Tone")
    include_offer: Optional[bool] = Field(None, description="Include offer")

class Authentication(BaseModel):
    auth_type: Optional[List[str]] = Field(None, description="Auth type")
    credentials: Optional[Dict[str, Any]] = Field(None, description="Credentials")

class RetryPolicy(BaseModel):
    max_retries: Optional[int] = Field(None, description="Max retries")
    backoff_strategy: Optional[List[str]] = Field(None, description="Backoff strategy")

# Module Configuration Models
class VisualAssetGenerator(BaseModel):
    prompt: Optional[str] = Field(None, description="Image generation prompt")
    brand_guidelines: Optional[BrandGuidelines] = Field(None, description="Brand guidelines")
    quantity: Optional[int] = Field(None, description="Number of images to generate")
    dimensions: Optional[Dimensions] = Field(None, description="Image dimensions")
    image_style: Optional[List[str]] = Field(None, description="Image style options")
    negative_prompts: Optional[List[str]] = Field(None, description="Negative prompts")

class VideoContentGenerator(BaseModel):
    content_type: Optional[List[str]] = Field(None, description="Content type options")
    script: Optional[str] = Field(None, description="Video script")
    image_inputs: Optional[List[str]] = Field(None, description="Input images")
    duration: Optional[int] = Field(None, description="Video duration in seconds")
    aspect_ratio: Optional[List[str]] = Field(None, description="Aspect ratio options")
    background_music: Optional[BackgroundMusic] = Field(None, description="Background music settings")
    voiceover: Optional[Voiceover] = Field(None, description="Voiceover settings")

class CopyContentGenerator(BaseModel):
    content_purpose: Optional[List[str]] = Field(None, description="Content purpose options")
    campaign_brief: Optional[str] = Field(None, description="Campaign brief")
    tone_of_voice: Optional[List[str]] = Field(None, description="Tone of voice options")
    target_audience: Optional[TargetAudience] = Field(None, description="Target audience")
    word_count_range: Optional[WordCountRange] = Field(None, description="Word count range")
    keywords: Optional[List[str]] = Field(None, description="Keywords")
    call_to_action: Optional[str] = Field(None, description="Call to action")
    variations: Optional[int] = Field(None, description="Number of variations")

class AudienceIntelligenceAnalyzer(BaseModel):
    product_category: Optional[str] = Field(None, description="Product category")
    geographic_location: Optional[GeographicLocation] = Field(None, description="Geographic location")
    campaign_objective: Optional[str] = Field(None, description="Campaign objective")
    existing_customer_data: Optional[ExistingCustomerData] = Field(None, description="Existing customer data")
    competitor_analysis: Optional[bool] = Field(None, description="Competitor analysis flag")

class CampaignTimelineOptimizer(BaseModel):
    campaign_duration: Optional[CampaignDuration] = Field(None, description="Campaign duration")
    content_inventory: Optional[List[ContentInventory]] = Field(None, description="Content inventory")
    audience_segments: Optional[List[str]] = Field(None, description="Audience segments")
    optimal_posting_times: Optional[OptimalPostingTimes] = Field(None, description="Optimal posting times")
    posting_frequency: Optional[PostingFrequency] = Field(None, description="Posting frequency")
    key_dates: Optional[List[KeyDate]] = Field(None, description="Key dates")
    budget_constraints: Optional[Dict[str, Any]] = Field(None, description="Budget constraints")

class ContentDistributionScheduler(BaseModel):
    optimized_timeline: Optional[List[TimelineSlot]] = Field(None, description="Optimized timeline")
    generated_copies: Optional[List[GeneratedCopy]] = Field(None, description="Generated copies")
    generated_images: Optional[List[GeneratedImage]] = Field(None, description="Generated images")
    video_url: Optional[str] = Field(None, description="Video URL")
    platform_specifications: Optional[PlatformSpecifications] = Field(None, description="Platform specifications")

class EmailSender(BaseModel):
    company_name: Optional[str] = Field(None, description="Company name")
    campaign_description: Optional[str] = Field(None, description="Campaign description")
    recipients: Optional[List[EmailRecipient]] = Field(None, description="Email recipients")
    sender_name: Optional[str] = Field(None, description="Sender name")
    email_subject: Optional[str] = Field(None, description="Email subject")

class ContentDistributionExecutor(BaseModel):
    distribution_schedule: Optional[List[ScheduleItem]] = Field(None, description="Distribution schedule")
    platform_credentials: Optional[PlatformCredentials] = Field(None, description="Platform credentials")
    execution_mode: Optional[List[str]] = Field(None, description="Execution mode")
    monitoring_enabled: Optional[bool] = Field(None, description="Monitoring enabled")
    rollback_on_failure: Optional[bool] = Field(None, description="Rollback on failure")

class OutreachCallScheduler(BaseModel):
    discovered_leads: Optional[List[DiscoveredLead]] = Field(None, description="Discovered leads")
    call_window_preferences: Optional[CallWindowPreferences] = Field(None, description="Call window preferences")
    campaign_duration: Optional[CampaignDuration] = Field(None, description="Campaign duration")
    calls_per_day: Optional[int] = Field(None, description="Calls per day")
    prioritization_criteria: Optional[PrioritizationCriteria] = Field(None, description="Prioritization criteria")

class VoiceInteractionAgent(BaseModel):
    call_schedule: Optional[List[CallSchedule]] = Field(None, description="Call schedule")
    conversation_objective: Optional[List[str]] = Field(None, description="Conversation objective")
    call_script: Optional[CallScript] = Field(None, description="Call script")
    voice_settings: Optional[VoiceSettings] = Field(None, description="Voice settings")
    max_call_duration: Optional[int] = Field(None, description="Max call duration")
    auto_dial: Optional[bool] = Field(None, description="Auto dial")

class LeadDiscoveryEngine(BaseModel):
    search_criteria: Optional[SearchCriteria] = Field(None, description="Search criteria")
    audience_segments: Optional[List[str]] = Field(None, description="Audience segments")
    data_sources: Optional[List[str]] = Field(None, description="Data sources")
    qualification_criteria: Optional[QualificationCriteria] = Field(None, description="Qualification criteria")
    max_leads: Optional[int] = Field(None, description="Max leads")
    enrichment_required: Optional[bool] = Field(None, description="Enrichment required")

class CollaborationOutreachComposer(BaseModel):
    target_profiles: Optional[List[TargetProfile]] = Field(None, description="Target profiles")
    discovered_leads: Optional[List[str]] = Field(None, description="Discovered leads")
    campaign_brief: Optional[str] = Field(None, description="Campaign brief")
    generated_copies: Optional[List[str]] = Field(None, description="Generated copies")
    outreach_type: Optional[List[str]] = Field(None, description="Outreach type")
    personalization_level: Optional[List[str]] = Field(None, description="Personalization level")
    template_guidelines: Optional[TemplateGuidelines] = Field(None, description="Template guidelines")

class ExternalApiOrchestrator(BaseModel):
    api_endpoint: Optional[str] = Field(None, description="API endpoint")
    http_method: Optional[List[str]] = Field(None, description="HTTP method")
    request_headers: Optional[Dict[str, Any]] = Field(None, description="Request headers")
    request_body: Optional[Dict[str, Any]] = Field(None, description="Request body")
    authentication: Optional[Authentication] = Field(None, description="Authentication")
    retry_policy: Optional[RetryPolicy] = Field(None, description="Retry policy")
    response_mapping: Optional[Dict[str, Any]] = Field(None, description="Response mapping")

class ModuleConfigurations(BaseModel):
    visual_asset_generator: Optional[VisualAssetGenerator] = Field(None, description="Visual asset generator configuration")
    copy_content_generator: Optional[CopyContentGenerator] = Field(None, description="Copy content generator configuration")
    audience_intelligence_analyzer: Optional[AudienceIntelligenceAnalyzer] = Field(None, description="Audience intelligence analyzer configuration")
    campaign_timeline_optimizer: Optional[CampaignTimelineOptimizer] = Field(None, description="Campaign timeline optimizer configuration")
    content_distribution_scheduler: Optional[ContentDistributionScheduler] = Field(None, description="Content distribution scheduler configuration")
    email_sender: Optional[EmailSender] = Field(None, description="Email sender configuration")

# Request/Response Models
class QuickCampaignRequest(BaseModel):
    brief: str = Field(..., description="Campaign brief description")

class CampaignRequest(BaseModel):
    product: str = Field(..., description="Product or service description")
    target_audience: str = Field(..., description="Target audience description")
    location: str = Field(..., description="Geographic location")
    occasion: Optional[str] = Field(None, description="Special occasion or season")
    budget: Optional[str] = Field(None, description="Budget range")

class ModuleConnection(BaseModel):
    target_module: str = Field(..., description="Target module name")
    source_output: str = Field(..., description="Source output field")
    target_input: str = Field(..., description="Target input field")

class ModuleConnections(BaseModel):
    module_name: str = Field(..., description="Module name")
    connections: List[ModuleConnection] = Field(..., description="Module connections")

class CampaignResponse(BaseModel):
    """Response model for campaign strategy"""
    campaign_brief: str = Field(..., description="Generated campaign brief")
    strategy_plan: str = Field(..., description="Detailed strategy plan")
    research_summary: str = Field(..., description="Summary of research conducted")
    sources: List[str] = Field(..., description="List of sources used")
    module_configurations: Optional[ModuleConfigurations] = Field(None, description="Prefilled module configurations")
    module_connections: Optional[List[ModuleConnections]] = Field(None, description="Module connections and data flow")
    timestamp: datetime = Field(default_factory=datetime.now)

# Visual Asset Generator Models
class VisualAssetRequest(BaseModel):
    prompt: str = Field(..., description="Image generation prompt")
    brand_guidelines: Optional[BrandGuidelines] = Field(None, description="Brand guidelines")
    quantity: int = Field(1, description="Number of images to generate")
    dimensions: Dimensions = Field(default_factory=lambda: Dimensions(width=512, height=512), description="Image dimensions")
    image_style: Optional[List[str]] = Field(["photorealistic"], description="Image style options")
    negative_prompts: Optional[List[str]] = Field(None, description="Negative prompts")

class GeneratedImageResponse(BaseModel):
    image_url: str = Field(..., description="Generated image URL")
    image_id: str = Field(..., description="Unique image ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Image metadata")

class GenerationMetadata(BaseModel):
    model_used: str = Field("pollinations-ai", description="Model used for generation")
    generation_time: datetime = Field(default_factory=datetime.now, description="Generation timestamp")
    prompt_tokens: Optional[int] = Field(None, description="Number of prompt tokens")

class VisualAssetResponse(BaseModel):
    outputs: Dict[str, Any] = Field(..., description="Generated outputs")
    generation_metadata: GenerationMetadata = Field(..., description="Generation metadata")
    execution_status: str = Field(..., description="Execution status")

# Copy Content Generator Models
class CopyContentRequest(BaseModel):
    content_purpose: List[str] = Field(..., description="Content purpose options")
    campaign_brief: str = Field(..., description="Campaign brief")
    tone_of_voice: List[str] = Field(..., description="Tone of voice options")
    target_audience: TargetAudience = Field(..., description="Target audience")
    word_count_range: WordCountRange = Field(..., description="Word count range")
    keywords: Optional[List[str]] = Field(None, description="Keywords")
    call_to_action: Optional[str] = Field(None, description="Call to action")
    variations: int = Field(1, description="Number of variations")

# Email Campaign Models
class EmailRecipient(BaseModel):
    name: str = Field(..., description="Recipient name")
    email: str = Field(..., description="Recipient email address")
    personal_description: str = Field(..., description="Personal interests and preferences")

class EmailCampaignRequest(BaseModel):
    company_name: str = Field(..., description="Company name")
    campaign_description: str = Field(..., description="Campaign description")
    recipients: List[EmailRecipient] = Field(..., description="List of email recipients")
    sender_name: Optional[str] = Field(None, description="Sender name (defaults to company name)")
    email_subject: Optional[str] = Field(None, description="Email subject (defaults to 'Special Offer from {company_name}!')")

class EmailDeliveryStatus(BaseModel):
    recipient_name: str = Field(..., description="Recipient name")
    recipient_email: str = Field(..., description="Recipient email")
    status: str = Field(..., description="Delivery status: 'sent', 'failed'")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    email_content: Optional[str] = Field(None, description="Generated email content")

class EmailCampaignResponse(BaseModel):
    campaign_summary: Dict[str, Any] = Field(..., description="Campaign summary")
    delivery_results: List[EmailDeliveryStatus] = Field(..., description="Email delivery results")
    execution_status: str = Field(..., description="Execution status: 'success', 'partial_success', 'failed'")
    timestamp: datetime = Field(default_factory=datetime.now, description="Execution timestamp")

class GeneratedCopyResponse(BaseModel):
    copy_text: str = Field(..., description="Generated content text")
    copy_id: str = Field(..., description="Unique identifier for the copy")
    word_count: int = Field(..., description="Actual word count")
    hashtags: List[str] = Field(..., description="Best hashtags")
    emojis: List[str] = Field(..., description="Best emojis")

class SEOMetadata(BaseModel):
    keyword_density: Dict[str, float] = Field(..., description="Keyword density analysis")
    readability_score: float = Field(..., description="Readability score")

class CopyContentResponse(BaseModel):
    outputs: Dict[str, Any] = Field(..., description="Generated outputs")
    execution_status: str = Field(..., description="Execution status")

# FastAPI App Setup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize agent on startup"""
    global agent
    try:
        agent = Agent(
            model=Gemini(id="gemini-2.0-flash"),
            tools=[
                ExaTools(start_published_date=calculate_start_date(30), type="keyword"),
                FirecrawlTools(),
            ],
            description="Expert social media campaign strategist with real-time market research capabilities",
            instructions=dedent("""
            You are an expert social media campaign strategist with access to real-time market research tools.
            Your role is to create comprehensive, data-driven campaign strategies that deliver measurable results.
            
            Key capabilities:
            - Real-time market trend analysis using ExaTools
            - Detailed competitor research and benchmarking
            - Audience behavior insights and segmentation
            - Budget optimization and ROI forecasting
            - Content strategy and creative direction
            - Platform-specific optimization recommendations
            
            Always base your recommendations on actual research data gathered from your tools.
            Provide specific, actionable insights with clear rationale and expected outcomes.
            """),
            expected_output="Comprehensive social media campaign strategy with detailed research findings, target audience analysis, content recommendations, budget allocation, timeline, and success metrics."
        )
        print("Agent initialized successfully")
    except Exception as e:
        print(f"Error initializing agent: {e}")
        agent = None
    yield
    # Cleanup on shutdown
    agent = None

app = FastAPI(
    title="Social Media Campaign Strategy API",
    description="AI-powered social media campaign planning with real-time market research",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def generate_key_dates_from_brief(campaign_brief: str) -> List[KeyDate]:
    """Generate key dates based on campaign brief and current month"""
    from datetime import datetime, timedelta
    
    brief_lower = campaign_brief.lower()
    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year
    
    key_dates = []
    
    # Generate dates based on campaign context
    if "launch" in brief_lower or "new" in brief_lower:
        # Product launch campaign
        launch_date = current_date + timedelta(days=7)
        key_dates.append(KeyDate(
            date=launch_date.strftime("%Y-%m-%d"),
            event="Product Launch",
            priority=["high"]
        ))
        
        # Pre-launch phase
        pre_launch = current_date + timedelta(days=3)
        key_dates.append(KeyDate(
            date=pre_launch.strftime("%Y-%m-%d"),
            event="Pre-Launch Campaign",
            priority=["medium"]
        ))
        
        # Post-launch follow-up
        follow_up = launch_date + timedelta(days=7)
        key_dates.append(KeyDate(
            date=follow_up.strftime("%Y-%m-%d"),
            event="Post-Launch Follow-up",
            priority=["medium"]
        ))
    
    elif "holiday" in brief_lower or "christmas" in brief_lower or "new year" in brief_lower:
        # Holiday campaign
        if current_month == 12:
            key_dates.append(KeyDate(
                date=f"{current_year}-12-25",
                event="Christmas Day",
                priority=["high"]
            ))
            key_dates.append(KeyDate(
                date=f"{current_year}-12-24",
                event="Christmas Eve",
                priority=["high"]
            ))
        elif current_month == 1:
            key_dates.append(KeyDate(
                date=f"{current_year}-01-01",
                event="New Year's Day",
                priority=["high"]
            ))
            key_dates.append(KeyDate(
                date=f"{current_year}-01-31",
                event="January Campaign End",
                priority=["medium"]
            ))
    
    elif "environment" in brief_lower or "earth day" in brief_lower or "sustainability" in brief_lower:
        # Environmental campaign
        if current_month == 4:
            key_dates.append(KeyDate(
                date=f"{current_year}-04-22",
                event="Earth Day",
                priority=["high"]
            ))
        else:
            # General environmental awareness
            env_date = current_date + timedelta(days=14)
            key_dates.append(KeyDate(
                date=env_date.strftime("%Y-%m-%d"),
                event="Environmental Awareness Day",
                priority=["high"]
            ))
    
    elif "fitness" in brief_lower or "health" in brief_lower or "wellness" in brief_lower:
        # Health/fitness campaign
        # New Year resolution period
        if current_month == 1:
            key_dates.append(KeyDate(
                date=f"{current_year}-01-01",
                event="New Year Fitness Resolution",
                priority=["high"]
            ))
            key_dates.append(KeyDate(
                date=f"{current_year}-01-15",
                event="Mid-January Check-in",
                priority=["medium"]
            ))
        else:
            # General fitness campaign
            fitness_date = current_date + timedelta(days=10)
            key_dates.append(KeyDate(
                date=fitness_date.strftime("%Y-%m-%d"),
                event="Fitness Challenge Launch",
                priority=["high"]
            ))
    
    elif "sale" in brief_lower or "discount" in brief_lower or "promotion" in brief_lower:
        # Sales campaign
        sale_start = current_date + timedelta(days=5)
        sale_end = sale_start + timedelta(days=7)
        
        key_dates.append(KeyDate(
            date=sale_start.strftime("%Y-%m-%d"),
            event="Sale Launch",
            priority=["high"]
        ))
        key_dates.append(KeyDate(
            date=sale_end.strftime("%Y-%m-%d"),
            event="Sale End",
            priority=["high"]
        ))
        
        # Mid-sale reminder
        mid_sale = sale_start + timedelta(days=3)
        key_dates.append(KeyDate(
            date=mid_sale.strftime("%Y-%m-%d"),
            event="Mid-Sale Reminder",
            priority=["medium"]
        ))
    
    else:
        # Default campaign timeline
        week1 = current_date + timedelta(days=7)
        week2 = current_date + timedelta(days=14)
        week3 = current_date + timedelta(days=21)
        week4 = current_date + timedelta(days=28)
        
        key_dates.extend([
            KeyDate(
                date=week1.strftime("%Y-%m-%d"),
                event="Week 1 Campaign Review",
                priority=["medium"]
            ),
            KeyDate(
                date=week2.strftime("%Y-%m-%d"),
                event="Mid-Campaign Assessment",
                priority=["medium"]
            ),
            KeyDate(
                date=week3.strftime("%Y-%m-%d"),
                event="Campaign Optimization",
                priority=["medium"]
            ),
            KeyDate(
                date=week4.strftime("%Y-%m-%d"),
                event="Campaign Conclusion",
                priority=["high"]
            )
        ])
    
    return key_dates

def generate_budget_constraints_from_brief(campaign_brief: str) -> Dict[str, Any]:
    """Generate budget constraints based on campaign brief"""
    brief_lower = campaign_brief.lower()
    
    # Default budget structure
    budget_constraints = {
        "daily_budget": 100,
        "total_budget": 3000,
        "platform_allocation": {
            "Instagram": 40,
            "Facebook": 30,
            "LinkedIn": 20,
            "Twitter": 10
        },
        "content_type_allocation": {
            "visual_content": 50,
            "video_content": 30,
            "text_content": 20
        }
    }
    
    # Adjust budget based on campaign context
    if "high budget" in brief_lower or "premium" in brief_lower or "enterprise" in brief_lower:
        budget_constraints.update({
            "daily_budget": 500,
            "total_budget": 15000,
            "platform_allocation": {
                "Instagram": 35,
                "Facebook": 25,
                "LinkedIn": 25,
                "TikTok": 15
            },
            "content_type_allocation": {
                "visual_content": 40,
                "video_content": 45,
                "text_content": 15
            }
        })
    
    elif "low budget" in brief_lower or "startup" in brief_lower or "small" in brief_lower:
        budget_constraints.update({
            "daily_budget": 25,
            "total_budget": 750,
            "platform_allocation": {
                "Instagram": 50,
                "Facebook": 30,
                "LinkedIn": 20
            },
            "content_type_allocation": {
                "visual_content": 60,
                "video_content": 20,
                "text_content": 20
            }
        })
    
    elif "medium budget" in brief_lower or "moderate" in brief_lower:
        budget_constraints.update({
            "daily_budget": 200,
            "total_budget": 6000,
            "platform_allocation": {
                "Instagram": 40,
                "Facebook": 30,
                "LinkedIn": 20,
                "Twitter": 10
            },
            "content_type_allocation": {
                "visual_content": 50,
                "video_content": 30,
                "text_content": 20
            }
        })
    
    # Adjust based on industry/context
    if "tech" in brief_lower or "software" in brief_lower or "app" in brief_lower:
        budget_constraints["platform_allocation"].update({
            "LinkedIn": 30,
            "Twitter": 20,
            "Instagram": 30,
            "Facebook": 20
        })
    
    elif "fashion" in brief_lower or "lifestyle" in brief_lower or "beauty" in brief_lower:
        budget_constraints["platform_allocation"].update({
            "Instagram": 50,
            "TikTok": 25,
            "Facebook": 15,
            "LinkedIn": 10
        })
        budget_constraints["content_type_allocation"].update({
            "visual_content": 70,
            "video_content": 25,
            "text_content": 5
        })
    
    elif "b2b" in brief_lower or "business" in brief_lower or "professional" in brief_lower:
        budget_constraints["platform_allocation"].update({
            "LinkedIn": 50,
            "Facebook": 25,
            "Twitter": 15,
            "Instagram": 10
        })
        budget_constraints["content_type_allocation"].update({
            "text_content": 40,
            "visual_content": 40,
            "video_content": 20
        })
    
    elif "food" in brief_lower or "restaurant" in brief_lower or "coffee" in brief_lower:
        budget_constraints["platform_allocation"].update({
            "Instagram": 45,
            "Facebook": 30,
            "TikTok": 15,
            "LinkedIn": 10
        })
        budget_constraints["content_type_allocation"].update({
            "visual_content": 60,
            "video_content": 30,
            "text_content": 10
        })
    
    # Add campaign-specific constraints
    if "30 days" in brief_lower or "month" in brief_lower:
        budget_constraints["campaign_duration"] = "30 days"
    elif "week" in brief_lower:
        budget_constraints["campaign_duration"] = "7 days"
        budget_constraints["total_budget"] = budget_constraints["daily_budget"] * 7
    elif "quarter" in brief_lower or "3 months" in brief_lower:
        budget_constraints["campaign_duration"] = "90 days"
        budget_constraints["total_budget"] = budget_constraints["daily_budget"] * 90
    
    return budget_constraints

def extract_module_configurations_fallback(campaign_brief: str) -> ModuleConfigurations:
    """Fallback module configuration extraction without external APIs"""
    
    # Simple keyword-based extraction
    brief_lower = campaign_brief.lower()
    
    # Extract basic information
    brand_name = None
    if "brand" in brief_lower:
        # Try to extract brand name
        words = campaign_brief.split()
        for i, word in enumerate(words):
            if word.lower() in ["brand", "company", "business"]:
                if i + 1 < len(words):
                    brand_name = words[i + 1]
                break
    
    # Extract target audience
    target_audience = None
    if "gen z" in brief_lower:
        target_audience = TargetAudience(
            product_description="Sustainable coffee brand",
            demographics="Gen Z (18-26 years old)",
            psychographics="Environmentally conscious, tech-savvy, social media active",
            pain_points=["Environmental concerns", "Quality vs sustainability", "Price sensitivity"]
        )
    elif "millennial" in brief_lower:
        target_audience = TargetAudience(
            product_description="Fitness app",
            demographics="Millennials (27-42 years old)",
            psychographics="Health-conscious, busy professionals, work-life balance seekers",
            pain_points=["Time constraints", "Motivation", "Consistency"]
        )
    elif "professional" in brief_lower:
        target_audience = TargetAudience(
            product_description="Professional services",
            demographics="Working professionals (25-45 years old)",
            psychographics="Career-focused, efficiency-oriented, quality-conscious",
            pain_points=["Time management", "ROI", "Competitive advantage"]
        )
    
    # Extract geographic location
    geographic_location = None
    if "mumbai" in brief_lower:
        geographic_location = GeographicLocation(
            country="India",
            city="Mumbai",
            region="Maharashtra"
        )
    elif "delhi" in brief_lower:
        geographic_location = GeographicLocation(
            country="India",
            city="Delhi",
            region="Delhi"
        )
    elif "bangalore" in brief_lower:
        geographic_location = GeographicLocation(
            country="India",
            city="Bangalore",
            region="Karnataka"
        )
    
    # Create module configurations
    visual_asset_generator = VisualAssetGenerator(
        prompt=f"Professional marketing visual for {campaign_brief}",
        brand_guidelines=BrandGuidelines(
            colors=["green", "blue", "white"],
            style="Modern and clean",
            logo_url=None
        ),
        quantity=5,
        dimensions=Dimensions(width=1080, height=1080),
        image_style=["photorealistic", "illustration", "minimal"],
        negative_prompts=["blurry", "low quality", "unprofessional"]
    )
    
    
    copy_content_generator = CopyContentGenerator(
        content_purpose=["social_caption", "ad_copy", "blog_post"],
        campaign_brief=campaign_brief,
        tone_of_voice=["professional", "casual", "inspirational"],
        target_audience=target_audience,
        word_count_range=WordCountRange(min=50, max=150),
        keywords=["sustainability", "innovation", "quality"],
        call_to_action="Learn more",
        variations=3
    )
    
    audience_intelligence_analyzer = AudienceIntelligenceAnalyzer(
        product_category="Food & Beverage" if "coffee" in brief_lower else "Technology" if "app" in brief_lower else "General",
        geographic_location=geographic_location,
        campaign_objective="Increase brand awareness and engagement",
        existing_customer_data=ExistingCustomerData(
            age_range="18-35",
            interests=["sustainability", "technology", "lifestyle"],
            behavior_patterns=["social media active", "mobile-first", "value-conscious"]
        ),
        competitor_analysis=True
    )
    
    campaign_timeline_optimizer = CampaignTimelineOptimizer(
        campaign_duration=CampaignDuration(
            start_date="2025-10-12",
            end_date="2025-12-31"
        ),
        content_inventory=[],
        audience_segments=["primary", "secondary"],
        optimal_posting_times=OptimalPostingTimes(
            platform="Instagram",
            time_slots=["09:00", "12:00", "18:00"]
        ),
        posting_frequency=PostingFrequency(
            min_posts_per_day=1,
            max_posts_per_day=3
        ),
        key_dates=generate_key_dates_from_brief(campaign_brief),
        budget_constraints=generate_budget_constraints_from_brief(campaign_brief)
    )
    
    content_distribution_scheduler = ContentDistributionScheduler(
        optimized_timeline=[],
        generated_copies=[],
        generated_images=[],
        video_url=None,
        platform_specifications=PlatformSpecifications(
            platform_name="Instagram",
            max_caption_length=2200,
            supported_formats=["image", "video", "carousel"],
            aspect_ratio_requirements="1:1, 4:5, 16:9"
        )
    )
    
    email_sender = EmailSender(
        company_name=brand_name or "Your Company",
        campaign_description=campaign_brief,
        recipients=[],
        sender_name=brand_name or "Your Company",
        email_subject=f"Special Offer from {brand_name or 'Your Company'}!"
    )
    
    return ModuleConfigurations(
        visual_asset_generator=visual_asset_generator,
        copy_content_generator=copy_content_generator,
        audience_intelligence_analyzer=audience_intelligence_analyzer,
        campaign_timeline_optimizer=campaign_timeline_optimizer,
        content_distribution_scheduler=content_distribution_scheduler,
        email_sender=email_sender
    )

def get_module_connections() -> List[ModuleConnections]:
    """Get predefined module connections for the workflow"""
    return [
        ModuleConnections(
            module_name="audience_intelligence_analyzer",
            connections=[
                ModuleConnection(
                    target_module="copy_content_generator",
                    source_output="audience_segments",
                    target_input="target_audience"
                ),
                ModuleConnection(
                    target_module="campaign_timeline_optimizer",
                    source_output="audience_segments",
                    target_input="audience_segments"
                ),
                ModuleConnection(
                    target_module="campaign_timeline_optimizer",
                    source_output="optimal_posting_times",
                    target_input="optimal_posting_times"
                )
            ]
        ),
        ModuleConnections(
            module_name="copy_content_generator",
            connections=[
                ModuleConnection(
                    target_module="visual_asset_generator",
                    source_output="generated_copies",
                    target_input="prompt"
                ),
                ModuleConnection(
                    target_module="content_distribution_scheduler",
                    source_output="generated_copies",
                    target_input="generated_copies"
                )
            ]
        ),
        ModuleConnections(
            module_name="visual_asset_generator",
            connections=[
                ModuleConnection(
                    target_module="content_distribution_scheduler",
                    source_output="generated_images",
                    target_input="generated_images"
                )
            ]
        ),
        ModuleConnections(
            module_name="campaign_timeline_optimizer",
            connections=[
                ModuleConnection(
                    target_module="content_distribution_scheduler",
                    source_output="optimized_timeline",
                    target_input="optimized_timeline"
                )
            ]
        ),
        ModuleConnections(
            module_name="content_distribution_scheduler",
            connections=[
                ModuleConnection(
                    target_module="email_sender",
                    source_output="distribution_schedule",
                    target_input="campaign_description"
                )
            ]
        ),
        ModuleConnections(
            module_name="email_sender",
            connections=[]
        )
    ]

# Routes
@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Social Media Campaign Strategy API",
        "version": "1.0.0",
        "status": "active",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "agent_ready": agent is not None,
        "timestamp": datetime.now()
    }

@app.post("/campaign/plan", response_model=CampaignResponse)
async def create_campaign_plan(request: CampaignRequest):
    """
    Create a comprehensive social media campaign plan
    
    This endpoint generates a detailed campaign strategy based on:
    - Product/service information
    - Target audience demographics
    - Geographic location
    - Special occasions or seasons
    - Budget considerations
    
    Note: This endpoint does NOT include module connections.
    Use /campaign/quick for module connections.
    """
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        # Construct campaign brief from request
        campaign_brief = f"""
        Create a social media campaign for:
        - Product/Service: {request.product}
        - Target Audience: {request.target_audience}
        - Location: {request.location}
        - Occasion: {request.occasion or 'General promotion'}
        - Budget: {request.budget or 'Medium budget'}
        """
        
        # Generate comprehensive strategy plan using agent
        strategy_prompt = f"""
        Create a comprehensive social media campaign strategy plan based on this brief:
        "{campaign_brief}"
        
        Use the available tools extensively for comprehensive research. Follow this process:
        1. Use ExaTools to search for '[product] marketing trends 2025'
        2. Use ExaTools to search for '[target audience] social media behavior [location]' 
        3. Use ExaTools to search for '[occasion] marketing campaigns successful'
        4. Use ExaTools to search for '[product category] competitors [location]'
        5. Use ExaTools to search for 'social media advertising costs [location] 2025'
        6. If any search returns limited results, use FirecrawlTools to scrape the most relevant pages
        7. Base ALL your recommendations (budget, timing, strategy) on the research data you gather
        8. Create strategic concepts and taglines inspired by successful examples from your research
        9. Always cite your sources and explain how tool data influenced your recommendations
        
        Create a detailed strategy plan that includes:
        - Research Summary
        - Target Audience Analysis  
        - Market Intelligence
        - Campaign Strategy
        - Budget & Timeline Recommendations
        - Sources & References
        
        Base your recommendations on actual data gathered from tool calls, not assumptions.
        """
        
        response = agent.run(strategy_prompt)
        strategy_plan = response.content if hasattr(response, 'content') else str(response)
        
        # Extract module configurations using LLM
        module_configurations = extract_module_configurations_fallback(campaign_brief)
        
        # Get module connections (null for this endpoint)
        module_connections = None
        
        # Extract sources
        sources = ["ExaTools research", "FirecrawlTools scraping"]
        
        return CampaignResponse(
            campaign_brief=campaign_brief,
            strategy_plan=strategy_plan,
            research_summary="Research conducted using ExaTools and FirecrawlTools with comprehensive field extraction",
            sources=sources,
            module_configurations=module_configurations,
            module_connections=module_connections
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating campaign plan: {str(e)}")

@app.post("/campaign/quick", response_model=CampaignResponse)
async def create_quick_campaign(request: QuickCampaignRequest):
    """
    Create a comprehensive social media campaign plan from a brief description
    
    This endpoint generates:
    1. A detailed campaign strategy plan using real-time research
    2. Prefilled module configurations for all content generation modules
    3. Module connections for workflow orchestration
    4. Extracted and inferred fields based on the campaign brief
    
    This is the ONLY endpoint that includes module connections.
    The module configurations and connections can be used directly for content generation workflows.
    """
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        # Check cache first
        cache_key = get_cache_key(request.brief)
        cached_response = response_cache.get(cache_key)
        
        if cached_response and is_cache_valid(cached_response):
            print("Using cached response to avoid rate limits")
            return CampaignResponse(**cached_response["data"])
        
        # Check rate limits before making API calls
        rate_limits = check_rate_limits()
        
        if not rate_limits["exa_available"] and not rate_limits["firecrawl_available"]:
            print("Rate limits exceeded, using fallback strategy...")
            raise Exception("Rate limit exceeded - using fallback")
        
        # Generate comprehensive strategy plan using agent with retry logic
        strategy_prompt = f"""
        Create a comprehensive social media campaign strategy plan based on this brief:
        "{request.brief}"
        
        Use the available tools extensively for comprehensive research. Follow this process:
        1. Use ExaTools to search for '[product] marketing trends 2025'
        2. Use ExaTools to search for '[target audience] social media behavior [location]' 
        3. Use ExaTools to search for '[occasion] marketing campaigns successful'
        4. Use ExaTools to search for '[product category] competitors [location]'
        5. Use ExaTools to search for 'social media advertising costs [location] 2025'
        6. If any search returns limited results, use FirecrawlTools to scrape the most relevant pages
        7. Base ALL your recommendations (budget, timing, strategy) on the research data you gather
        8. Create strategic concepts and taglines inspired by successful examples from your research
        9. Always cite your sources and explain how tool data influenced your recommendations
        
        Create a detailed strategy plan that includes:
        - Research Summary
        - Target Audience Analysis  
        - Market Intelligence
        - Campaign Strategy
        - Budget & Timeline Recommendations
        - Sources & References
        
        Base your recommendations on actual data gathered from tool calls, not assumptions.
        """
        
        # Use retry logic for agent calls
        async def run_agent():
            return agent.run(strategy_prompt)
        
        response = await retry_with_backoff(run_agent)
        strategy_plan = response.content if hasattr(response, 'content') else str(response)
        
        # Update rate limit counters
        rate_limit_tracker["exa_requests_count"] += 1
        rate_limit_tracker["firecrawl_requests_count"] += 1
        
        # Extract module configurations using LLM with retry
        async def extract_configs():
            return extract_module_configurations_fallback(request.brief)
        
        module_configurations = await retry_with_backoff(extract_configs)
        
        # Get module connections
        module_connections = get_module_connections()
        
        # Extract sources
        sources = ["ExaTools research", "FirecrawlTools scraping"]
        
        response_data = CampaignResponse(
            campaign_brief=request.brief,
            strategy_plan=strategy_plan,
            research_summary="Research conducted using ExaTools and FirecrawlTools with comprehensive field extraction",
            sources=sources,
            module_configurations=module_configurations,
            module_connections=module_connections
        )
        
        # Cache the response
        response_cache[cache_key] = {
            "data": response_data.dict(),
            "timestamp": time.time()
        }
        
        return response_data
        
    except Exception as e:
        # Check if it's a rate limiting error
        if "429" in str(e) or "Too Many Requests" in str(e):
            print("Rate limit hit, using fallback strategy generation...")
            
            # Generate fallback strategy without external APIs
            fallback_strategy = f"""
            # Campaign Strategy for: {request.brief}
            
            ## Campaign Overview
            Based on your brief, here's a comprehensive social media campaign strategy:
            
            ### Target Audience Analysis
            - Primary audience: {request.brief.split('targeting')[1].split('for')[0].strip() if 'targeting' in request.brief else 'General audience'}
            - Geographic focus: {request.brief.split('in')[1].split('for')[0].strip() if 'in' in request.brief else 'Global'}
            - Campaign context: {request.brief.split('for')[1].strip() if 'for' in request.brief else 'General promotion'}
            
            ### Content Strategy
            1. **Visual Content**: Create engaging visuals that align with your brand
            2. **Copy Strategy**: Develop compelling copy that resonates with your target audience
            3. **Platform Optimization**: Tailor content for each social media platform
            4. **Engagement Tactics**: Use interactive elements to boost engagement
            
            ### Campaign Timeline
            - Duration: 30 days
            - Phase 1 (Days 1-10): Brand awareness and introduction
            - Phase 2 (Days 11-20): Engagement and community building
            - Phase 3 (Days 21-30): Conversion and retention
            
            ### Success Metrics
            - Reach and impressions
            - Engagement rate
            - Click-through rate
            - Conversion rate
            
            Note: This strategy was generated using fallback logic due to API rate limits.
            """
            
            # Use fallback module configurations
            module_configurations = extract_module_configurations_fallback(request.brief)
            
            # Get module connections
            module_connections = get_module_connections()
            
            return CampaignResponse(
                campaign_brief=request.brief,
                strategy_plan=fallback_strategy,
                research_summary="Strategy generated using fallback logic (external APIs rate limited)",
                sources=["Fallback strategy generation", "Keyword-based extraction"],
                module_configurations=module_configurations,
                module_connections=module_connections
            )
        else:
            raise HTTPException(status_code=500, detail=f"Error generating quick campaign: {str(e)}")

@app.get("/campaign/examples")
async def get_campaign_examples():
    """Get example campaign briefs for inspiration"""
    return {
        "examples": [
            {
                "title": "Sustainable Coffee Brand",
                "brief": "Launch a social media campaign for our new sustainable coffee brand targeting Gen Z in Mumbai for World Environment Day",
                "category": "Food & Beverage"
            },
            {
                "title": "Fitness App",
                "brief": "Create a fitness app campaign targeting millennials in Delhi with high budget for Q1 launch",
                "category": "Health & Fitness"
            },
            {
                "title": "Eco-Friendly Fashion",
                "brief": "Promote our eco-friendly fashion brand to environmentally conscious consumers in Bangalore",
                "category": "Fashion & Lifestyle"
            }
        ]
    }

@app.get("/agent/config")
async def get_agent_config():
    """Get current agent configuration"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    return {
        "model": "gemini-2.0-flash",
        "tools": ["ExaTools", "FirecrawlTools"],
        "research_period_days": 30,
        "capabilities": [
            "Market trend analysis",
            "Competitor research",
            "Audience insights",
            "Campaign strategy development",
            "Budget recommendations",
            "Timeline planning"
        ]
    }

@app.get("/rate-limits")
async def get_rate_limit_status():
    """Get current rate limit status"""
    rate_limits = check_rate_limits()
    current_time = time.time()
    
    return {
        "exa_status": {
            "available": rate_limits["exa_available"],
            "requests_count": rate_limit_tracker["exa_requests_count"],
            "last_reset": rate_limit_tracker["exa_last_reset"],
            "time_until_reset": max(0, 3600 - (current_time - rate_limit_tracker["exa_last_reset"]))
        },
        "firecrawl_status": {
            "available": rate_limits["firecrawl_available"],
            "requests_count": rate_limit_tracker["firecrawl_requests_count"],
            "last_reset": rate_limit_tracker["firecrawl_last_reset"],
            "time_until_reset": max(0, 3600 - (current_time - rate_limit_tracker["firecrawl_last_reset"]))
        },
        "cache_status": {
            "cached_responses": len(response_cache),
            "cache_duration_hours": CACHE_DURATION / 3600
        }
    }

@app.post("/clear-cache")
async def clear_cache():
    """Clear response cache"""
    global response_cache
    response_cache.clear()
    return {"message": "Cache cleared successfully", "timestamp": datetime.now()}

@app.get("/module/connections")
async def get_module_connections_endpoint():
    """Get module connections structure"""
    connections = get_module_connections()
    return {
        "total_modules": len(connections),
        "module_connections": connections,
        "description": "Predefined workflow connections between content generation modules"
    }

@app.post("/visual_asset_generator", response_model=VisualAssetResponse)
async def generate_visual_assets(request: VisualAssetRequest):
    """
    Generate visual assets using Pollinations AI
    
    This endpoint generates images based on:
    - Prompt description
    - Brand guidelines (colors, style, logo)
    - Quantity of images needed
    - Dimensions (width, height)
    - Image style preferences
    - Negative prompts to avoid
    """
    try:
        # Enhance prompt with brand guidelines if provided
        enhanced_prompt = request.prompt
        
        if request.brand_guidelines:
            if request.brand_guidelines.colors:
                color_text = ", ".join(request.brand_guidelines.colors)
                enhanced_prompt += f", {color_text} color scheme"
            
            if request.brand_guidelines.style:
                enhanced_prompt += f", {request.brand_guidelines.style} style"
        
        # Add negative prompts if provided
        if request.negative_prompts:
            negative_text = ", ".join(request.negative_prompts)
            enhanced_prompt += f", avoid {negative_text}"
        
        # Determine image style based on request
        image_style = "photorealistic"
        if request.image_style:
            if "illustration" in request.image_style:
                image_style = "illustration"
            elif "minimal" in request.image_style:
                image_style = "minimal"
            elif "abstract" in request.image_style:
                image_style = "abstract"
        
        # Prepare arguments for the visual_asset_manager
        args = {
            "prompt": enhanced_prompt,
            "quantity": request.quantity,
            "dimensions": {
                "width": request.dimensions.width,
                "height": request.dimensions.height
            },
            "image_style": image_style
        }
        
        # Generate images using the image.py service
        result = visual_asset_manager(args)
        
        # Check for errors
        if "error" in result:
            raise HTTPException(status_code=400, detail=f"Image generation error: {result['error']}")
        
        image_urls = result.get("image_urls", [])
        
        # Process results and create response
        generated_images = []
        successful_images = 0
        failed_images = 0
        
        for i, image_url in enumerate(image_urls):
            if isinstance(image_url, str):  # Successful generation
                image_response = GeneratedImageResponse(
                    image_url=image_url,
                    image_id=f"img_{int(time.time())}_{i}",
                    metadata={
                        "prompt": enhanced_prompt,
                        "style": image_style,
                        "dimensions": {
                            "width": request.dimensions.width,
                            "height": request.dimensions.height
                        },
                        "generation_index": i
                    }
                )
                generated_images.append(image_response)
                successful_images += 1
            else:  # Error case
                failed_images += 1
        
        # Determine execution status
        if successful_images == request.quantity:
            execution_status = "success"
        elif successful_images > 0:
            execution_status = "partial_success"
        else:
            execution_status = "failed"
        
        # Create response
        response = VisualAssetResponse(
            outputs={
                "generated_images": generated_images
            },
            generation_metadata=GenerationMetadata(
                model_used="pollinations-ai",
                generation_time=datetime.now(),
                prompt_tokens=len(enhanced_prompt.split())
            ),
            execution_status=execution_status
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating visual assets: {str(e)}")

@app.post("/audience_intelligence_analyzer", response_model=AudienceIntelligenceResponse)
async def analyze_audience(request: AudienceIntelligenceRequest):
    """
    Analyze audience intelligence and generate comprehensive insights
    
    This endpoint performs deep audience analysis including:
    - Audience segmentation with demographics and psychographics
    - Detailed persona profiles
    - Platform recommendations
    - Optimal posting times
    - Content preferences
    
    Uses LLM-powered analysis with real-time research capabilities.
    """
    try:
        print(f"🎯 Analyzing audience intelligence for {request.product_category} in {request.geographic_location.city or request.geographic_location.country}")
        
        # Call the audience intelligence analyzer
        result = analyze_audience_intelligence(request)
        
        print(f"✅ Analysis completed with status: {result.execution_status}")
        print(f"📊 Generated {len(result.outputs.get('audience_segments', []))} audience segments")
        print(f"👥 Created {len(result.outputs.get('persona_profiles', []))} persona profiles")
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing audience intelligence: {str(e)}")

@app.post("/copy_content_generator", response_model=CopyContentResponse)
async def generate_copy_content(request: CopyContentRequest):
    """
    Generate marketing copy content using AI
    
    This endpoint generates various types of marketing content including:
    - Social media captions
    - Ad copy
    - Blog posts
    - Email content
    - Educational content
    
    Uses LLM-powered content generation with SEO optimization.
    """
    try:
        print(f"📝 Generating copy content for: {request.campaign_brief}")
        print(f"🎯 Content purposes: {request.content_purpose}")
        print(f"🎨 Tone of voice: {request.tone_of_voice}")
        
        # Generate content for each purpose
        all_generated_copies = []
        
        for content_type in request.content_purpose:
            for tone in request.tone_of_voice:
                try:
                    # Prepare target audience data
                    target_audience_data = {
                        "demographics": request.target_audience.demographics or "General audience",
                        "psychographics": request.target_audience.psychographics or "General interests",
                        "pain_points": request.target_audience.pain_points or ["General concerns"]
                    }
                    
                    # Generate content using the copy_content_generator
                    result = generate_social_content(
                        content_type=content_type,
                        campaign_brief=request.campaign_brief,
                        tone_of_voice=tone,
                        target_audience=target_audience_data,
                        word_count_range={
                            "min": request.word_count_range.min or 50,
                            "max": request.word_count_range.max or 150
                        }
                    )
                    
                    # Process generated copies
                    if "generated_copies" in result:
                        for copy_data in result["generated_copies"]:
                            # Add keywords and CTA if provided
                            copy_text = copy_data.get("copy_text", "")
                            
                            # Enhance copy with keywords if provided
                            if request.keywords:
                                keyword_text = ", ".join(request.keywords[:3])  # Use top 3 keywords
                                copy_text += f" {keyword_text}"
                            
                            # Add call to action if provided
                            if request.call_to_action:
                                copy_text += f" {request.call_to_action}"
                            
                            # Create response object
                            copy_response = GeneratedCopyResponse(
                                copy_text=copy_text,
                                copy_id=f"{content_type}_{tone}_{len(all_generated_copies) + 1}",
                                word_count=len(copy_text.split()),
                                hashtags=copy_data.get("hashtags", []),
                                emojis=copy_data.get("emojis", [])
                            )
                            
                            all_generated_copies.append(copy_response)
                            
                            # Limit variations if specified
                            if len(all_generated_copies) >= request.variations:
                                break
                    
                    if len(all_generated_copies) >= request.variations:
                        break
                        
                except Exception as e:
                    print(f"Error generating {content_type} with {tone} tone: {e}")
                    continue
        
        # Calculate SEO metadata
        seo_metadata = calculate_seo_metadata(all_generated_copies, request.keywords)
        
        # Create response
        response = CopyContentResponse(
            outputs={
                "generated_copies": all_generated_copies,
                "seo_metadata": seo_metadata
            },
            execution_status="success" if all_generated_copies else "failed"
        )
        
        print(f"✅ Generated {len(all_generated_copies)} copy variations")
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating copy content: {str(e)}")

def calculate_seo_metadata(copies: List[GeneratedCopyResponse], keywords: Optional[List[str]]) -> SEOMetadata:
    """Calculate SEO metadata for generated copies"""
    
    if not copies:
        return SEOMetadata(
            keyword_density={},
            readability_score=0.0
        )
    
    # Calculate keyword density
    keyword_density = {}
    if keywords:
        all_text = " ".join([copy.copy_text.lower() for copy in copies])
        total_words = len(all_text.split())
        
        for keyword in keywords:
            keyword_count = all_text.count(keyword.lower())
            density = (keyword_count / total_words) * 100 if total_words > 0 else 0
            keyword_density[keyword] = round(density, 2)
    
    # Calculate average readability score (simplified)
    avg_word_count = sum(len(copy.copy_text.split()) for copy in copies) / len(copies)
    readability_score = min(100, max(0, 100 - (avg_word_count - 50) * 0.5))
    
    return SEOMetadata(
        keyword_density=keyword_density,
        readability_score=round(readability_score, 1)
    )

@app.post("/campaign_timeline_optimizer", response_model=CampaignTimelineResponse)
async def optimize_timeline(request: CampaignTimelineRequest):
    """
    Optimize campaign timeline using AI-powered scheduling
    
    This endpoint creates strategic campaign timelines including:
    - Real-time date analysis and event detection
    - Audience behavior pattern analysis
    - Platform-specific optimal posting times
    - Content distribution scheduling
    - Budget-aware timeline optimization
    - Engagement maximization strategies
    
    Uses LLM-powered analysis with web search capabilities.
    """
    try:
        print(f"📅 Optimizing campaign timeline from {request.campaign_duration.start_date} to {request.campaign_duration.end_date}")
        print(f"🎯 Audience segments: {request.audience_segments}")
        print(f"📱 Content inventory: {len(request.content_inventory)} items")
        
        # Call the campaign timeline optimizer
        result = optimize_campaign_timeline(request)
        
        print(f"✅ Timeline optimization completed with status: {result.execution_status}")
        print(f"📊 Generated {len(result.outputs.get('optimized_timeline', []))} timeline slots")
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error optimizing campaign timeline: {str(e)}")

@app.post("/content_distribution_scheduler", response_model=ContentDistributionResponse)
async def schedule_content_distribution_endpoint(request: ContentDistributionRequest):
    """
    Schedule content distribution with detailed posting plans
    
    This endpoint creates detailed posting schedules including:
    - Specific content assignments to timeline slots
    - Platform-optimized copy text and assets
    - Detailed posting parameters (hashtags, mentions, location tags)
    - Platform compliance checking
    - Execution notes and optimization recommendations
    - Comprehensive schedule summaries
    
    Takes optimized timeline from campaign_timeline_optimizer and content assets
    from copy_content_generator and visual_asset_generator to create actionable
    posting schedules.
    """
    try:
        print(f"📅 Scheduling content distribution for {len(request.optimized_timeline)} timeline slots")
        print(f"📝 Available copies: {len(request.generated_copies)}")
        print(f"🖼️ Available images: {len(request.generated_images) if request.generated_images else 0}")
        print(f"📱 Platform: {request.platform_specifications.platform_name}")
        
        # Call the content distribution scheduler
        result = schedule_content_distribution(request)
        
        print(f"✅ Content distribution scheduling completed with status: {result.execution_status}")
        print(f"📊 Generated {len(result.outputs.get('distribution_schedule', []))} schedule items")
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scheduling content distribution: {str(e)}")

@app.post("/email_campaign", response_model=EmailCampaignResponse)
async def send_email_campaign_endpoint(request: EmailCampaignRequest):
    """
    Send personalized email campaign using AI-generated content
    
    This endpoint sends personalized marketing emails to a list of recipients including:
    - AI-generated personalized email content for each recipient
    - Personalized subject lines and sender information
    - Campaign-specific messaging based on recipient interests
    - Delivery status tracking for each email
    - Comprehensive campaign summary and results
    
    This endpoint can use either:
    1. SendGrid API (recommended for cloud deployments) - set SENDGRID_API_KEY
    2. Gmail SMTP (fallback) - set SENDER_EMAIL and SENDER_PASSWORD
    
    Requirements:
    Option 1 - SendGrid (Recommended for Render):
    - SENDGRID_API_KEY environment variable
    - SENDER_EMAIL environment variable (verified in SendGrid)
    - GROQ_API_KEY environment variable
    
    Option 2 - Gmail SMTP (Fallback):
    - SENDER_EMAIL environment variable
    - SENDER_PASSWORD environment variable (Gmail app password)
    - GROQ_API_KEY environment variable
    """
    try:
        print(f"📧 Starting email campaign for {request.company_name}")
        print(f"📝 Campaign: {request.campaign_description}")
        print(f"👥 Recipients: {len(request.recipients)}")
        
        # Validate recipients
        if not request.recipients or len(request.recipients) == 0:
            raise HTTPException(
                status_code=400,
                detail="No recipients provided. Please include at least one recipient in the request."
            )
        
        # Check if SendGrid is available and configured
        sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
        
        if SENDGRID_AVAILABLE and sendgrid_api_key:
            # Use SendGrid API (better for cloud platforms)
            print("📬 Using SendGrid API for email delivery")
            result = send_email_campaign_sendgrid(request)
        else:
            # Fall back to SMTP
            if not sendgrid_api_key:
                print("⚠️ SENDGRID_API_KEY not set, falling back to SMTP")
            print("📬 Using Gmail SMTP for email delivery")
            result = send_email_campaign(request)
        
        print(f"✅ Email campaign completed: {result.campaign_summary['successful_sends']}/{result.campaign_summary['total_recipients']} emails sent successfully")
        return result
        
    except ValueError as ve:
        # Configuration errors (missing env variables, etc.)
        error_detail = str(ve)
        print(f"❌ Configuration error: {error_detail}")
        raise HTTPException(status_code=400, detail=error_detail)
        
    except Exception as e:
        # General errors
        error_detail = str(e)
        print(f"❌ Email campaign error: {error_detail}")
        
        # Return more detailed error information
        import traceback
        traceback_str = traceback.format_exc()
        print(f"Traceback:\n{traceback_str}")
        
        raise HTTPException(
            status_code=500,
            detail=f"Error sending email campaign: {error_detail}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
