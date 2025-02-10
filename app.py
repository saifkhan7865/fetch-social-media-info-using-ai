import streamlit as st
import os
from langchain.chat_models import ChatOpenAI
from dotenv import load_dotenv
from langchain.llms import OpenAI
from langchain.agents import initialize_agent, Tool
from langchain.agents import AgentType
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
import instaloader
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import pickle
from isodate import parse_duration
from datetime import datetime, timedelta
import requests
from unsplash.api import Api
from unsplash.auth import Auth
# Load environment variables
load_dotenv()

# Initialize Instagram loader
L = instaloader.Instaloader()

def get_instagram_info(username):
    try:
        # Remove '@' if present
        username = username.lstrip('@')
        
        print('searching for this username = ', username)
        # Get profile information
        profile = instaloader.Profile.from_username(L.context, username)
        
        # Fetch posts and analyze hashtags
        hashtags = {}
        post_types = {'image': 0, 'video': 0}
        total_likes = 0
        total_comments = 0
        post_count = 0
        
        for post in profile.get_posts():
            post_count += 1
            total_likes += post.likes
            total_comments += post.comments
            
            # Count post types
            if post.is_video:
                post_types['video'] += 1
            else:
                post_types['image'] += 1
            
            # Collect hashtags
            for tag in post.caption_hashtags:
                hashtags[tag] = hashtags.get(tag, 0) + 1
            
            # Limit to last 20 posts for performance
            if post_count >= 20:
                break
        
        # Calculate engagement rate
        avg_engagement = (total_likes + total_comments) / (post_count * profile.followers) * 100 if post_count > 0 and profile.followers > 0 else 0
        
        info = {
            'username': profile.username,
            'full_name': profile.full_name,
            'bio': profile.biography,
            'followers': profile.followers,
            'following': profile.followees,
            'total_posts': profile.mediacount,
            'is_private': profile.is_private,
            'analyzed_posts': post_count,
            'post_types': post_types,
            'top_hashtags': dict(sorted(hashtags.items(), key=lambda x: x[1], reverse=True)[:10]),
            'avg_engagement_rate': round(avg_engagement, 2)
        }
        return info
    except Exception as e:
        return f"Error fetching Instagram profile: {str(e)}"

def get_youtube_info(channel_url):
    try:
        # YouTube API setup
        api_key = os.getenv('YOUTUBE_API_KEY')
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # Extract channel ID from URL
        if 'channel/' in channel_url:
            channel_id = channel_url.split('channel/')[1].split('/')[0]
        elif '@' in channel_url:
            # Handle new @username format
            username = channel_url.split('@')[1].split('/')[0]
            
            print('this is the user name that we received', username)
            
            st.write('this is the user name that we received', username)
            # Try legacy lookup using forUsername (may fail for custom handles)
            request = youtube.channels().list(
                part='id',
                forHandle='@'+username
            )
            response = request.execute()
        
            if response.get('items'):
                channel_id = response['items'][0]['id']
            else:
                # Fallback: use search to resolve the custom handle to a channel ID
                search_request = youtube.search().list(
                    part='snippet',
                    q=username,
                    type='channel',
                    maxResults=1
                )
                search_response = search_request.execute()
                if search_response.get('items'):
                    channel_id = search_response['items'][0]['id']['channelId']
                else:
                    raise Exception(f"Could not find channel for username: {username}")
        else:
            raise Exception("Invalid channel URL format")
        
        # Get channel statistics and snippet
        channel_request = youtube.channels().list(
            part='statistics,snippet',
            id=channel_id
        )
        channel_response = channel_request.execute()
        channel_info = channel_response['items'][0]
        
        # Get recent videos from the channel
        videos_request = youtube.search().list(
            part='snippet',
            channelId=channel_id,
            order='date',
            type='video',
            maxResults=20
        )
        videos_response = videos_request.execute()
        
        # Extract video IDs from search results
        # Get the latest 10 videos with their details
        videos_data = []
        for video in videos_response['items'][:10]:
            if 'videoId' in video['id']:
                video_data = {
                    'title': video['snippet']['title'],
                    'description': video['snippet']['description'],
                    'published_at': video['snippet']['publishedAt']
                }
                videos_data.append(video_data)
        
        return {
            'channel_name': channel_info['snippet']['title'],
            'description': channel_info['snippet']['description'],
            'subscriber_count': int(channel_info['statistics']['subscriberCount']),
            'video_count': int(channel_info['statistics']['videoCount']),
            'view_count': int(channel_info['statistics']['viewCount']),
            'recent_videos': videos_data
        }
    except Exception as e:
        return f"Error fetching YouTube channel: {str(e)}"

def get_unsplash_images(query, count=3):
    try:
        # Initialize Unsplash client
        client_id = os.getenv('UNSPLASH_ACCESS_KEY')
        if not client_id:
            st.error("Unsplash API key not found. Please check your environment variables.")
            return []

        auth = Auth(client_id)
        api = Api(auth)

        # Clean and prepare the query
        query = query.strip()
        if not query:
            st.warning("No search keywords provided for image search")
            return []

        # Search for photos with error handling
        try:
            photos = api.photo.search(query=query, per_page=count)
            if not photos:
                st.warning(f"No photos found for query: {query}")
                return []

            # Return photo URLs with fallback to small size if regular is not available
            urls = []
            for photo in photos:
                if hasattr(photo, 'urls'):
                    url = photo.urls.regular or photo.urls.small
                    if url:
                        urls.append(url)

            if not urls:
                st.warning("Retrieved photos but no valid URLs found")
                return []

            return urls

        except Exception as search_error:
            st.error(f"Error searching Unsplash photos: {str(search_error)}")
            return []

    except Exception as e:
        st.error(f"Error initializing Unsplash client: {str(e)}")
        return []


def process_social_media_url(url):
    if 'instagram.com' in url:
        return {'platform': 'instagram', 'username': url.split('instagram.com/')[1].split('/')[0]}
    elif 'youtube.com' in url:
        return {'platform': 'youtube', 'url': url}
    elif 'twitter.com' in url or 'x.com' in url:
        return {'platform': 'twitter', 'username': url.split('/')[-1]}
    elif 'tiktok.com' in url:
        return {'platform': 'tiktok', 'username': url.split('/@')[-1].split('?')[0]}
    return None

def get_product_recommendations(profile_info, openai_api_key, platform='instagram'):
    try:
        if not openai_api_key:
            return "Please provide an OpenAI API key to get product recommendations."
        
        llm = ChatOpenAI(openai_api_key=openai_api_key, temperature=0.7, model_name="gpt-3.5-turbo")
        
        # Platform-specific templates
        templates = {
            'instagram': """Based on the following Instagram profile information, analyze and suggest 5 digital products that would be most suitable for this creator to sell to their audience. For each product:
1. Specify the product category (e.g., Course, Ebook, Template, Membership, Software Tool)
2. Provide a specific product recommendation
3. Explain why it would work well for this audience
4. Suggest relevant keywords for finding product imagery

Profile Information:
{profile_info}

Format each recommendation as:
Product 1:
- Category: [category]
- Product: [specific product name/description]
- Reasoning: [explanation]
- Image Keywords: [3-4 keywords for visuals]

[Repeat for all 5 products]""",
            
            'youtube': """Based on the following YouTube channel information, analyze and suggest 5 digital products that would be most suitable for this creator to sell to their audience. For each product:
1. Specify the product category (e.g., Course, Ebook, Template, Membership, Software Tool)
2. Provide a specific product recommendation
3. Explain why it would work well for this audience
4. Suggest relevant keywords for finding product imagery

Channel Information:
{profile_info}

Format each recommendation as:
Product 1:
- Category: [category]
- Product: [specific product name/description]
- Reasoning: [explanation]
- Image Keywords: [3-4 keywords for visuals]

[Repeat for all 5 products]"""
        }
        
        prompt = PromptTemplate(
            input_variables=["profile_info"],
            template=templates.get(platform, templates['instagram'])
        )
        
        chain = LLMChain(llm=llm, prompt=prompt)
        
        # Format profile info based on platform
        if platform == 'instagram':
            profile_summary = f"""- Audience size: {profile_info['followers']} followers
- Content focus: Top hashtags include {', '.join(list(profile_info['top_hashtags'].keys())[:5])}
- Engagement rate: {profile_info['avg_engagement_rate']}%
- Content mix: {profile_info['post_types']['image']} images, {profile_info['post_types']['video']} videos
- Bio: {profile_info['bio']}"""
        
        elif platform == 'youtube':
            profile_summary = f"""- Channel name: {profile_info['channel_name']}
- Subscriber count: {profile_info['subscriber_count']:,}
- Total views: {profile_info['view_count']:,}
- Channel description: {profile_info['description']}"""
        
        elif platform == 'twitter':
            profile_summary = f"""- Followers: {profile_info['followers']:,}
- Average engagement: {profile_info['avg_engagement']}
- Total tweets: {profile_info['total_tweets']:,}
- Profile description: {profile_info['description']}"""
        
        elif platform == 'tiktok':
            profile_summary = f"""- Followers: {profile_info['followers']:,}
- Total likes: {profile_info['total_likes']:,}
- Video count: {profile_info['video_count']:,}
- Average engagement: {profile_info['avg_engagement']}"""
        
        recommendations = chain.run(profile_summary)
        return recommendations
    except Exception as e:
        return f"Error generating recommendations: {str(e)}"

# Streamlit UI
st.title('Social Media Profile Analyzer & Product Recommender')

# Get OpenAI API key from environment variables
openai_api_key = os.getenv('OPENAI_API_KEY')
if not openai_api_key:
    st.error('OpenAI API key not found in environment variables. Please add OPENAI_API_KEY to your .env file.')
    st.stop()

# Social media platform selection
platform = st.selectbox('Select Platform:', ['Instagram', 'YouTube'])

# URL input
profile_url = st.text_input(f'Enter the {platform} profile URL:')

if st.button('Analyze Profile') and profile_url:
    profile_data = process_social_media_url(profile_url)
    
    if profile_data:
        with st.spinner('Fetching profile information...'):
            if profile_data['platform'] == 'instagram':
                info = get_instagram_info(profile_data['username'])
                if isinstance(info, dict):
                    st.subheader('Profile Information')
                    st.write(f"Username: {info['username']}")
                    st.write(f"Full Name: {info['full_name']}")
                    st.write(f"Bio: {info['bio']}")
                    st.write(f"Followers: {info['followers']:,}")
                    st.write(f"Following: {info['following']:,}")
                    st.write(f"Total Posts: {info['total_posts']:,}")
                    st.write(f"Private Account: {'Yes' if info['is_private'] else 'No'}")
                    
                    if not info['is_private']:
                        st.subheader('Content Analysis')
                        st.write(f"Analyzed Posts: Last {info['analyzed_posts']} posts")
                        st.write(f"Average Engagement Rate: {info['avg_engagement_rate']}%")
                        st.write("Content Mix:")
                        st.write(f"- Images: {info['post_types']['image']}")
                        st.write(f"- Videos: {info['post_types']['video']}")
                        
                        st.subheader('Top Hashtags')
                        for tag, count in info['top_hashtags'].items():
                            st.write(f"#{tag}: {count} posts")
                        
                        st.subheader('Digital Product Recommendations')
                        with st.spinner('Generating recommendations...'):
                            recommendations = get_product_recommendations(info, openai_api_key)
                            st.write(recommendations)
                else:
                    st.error(info)
                    
            elif profile_data['platform'] == 'youtube':
                info = get_youtube_info(profile_data['url'])
                if isinstance(info, dict):
                    st.subheader('Channel Information')
                    st.write(f"Channel Name: {info['channel_name']}")
                    st.write(f"Description: {info['description']}")
                    st.write(f"Subscribers: {info['subscriber_count']:,}")
                    st.write(f"Total Videos: {info['video_count']:,}")
                    st.write(f"Total Views: {info['view_count']:,}")
                    
                    st.subheader('Recent Videos')
                    for video in info['recent_videos']:
                        st.write(f"Title: {video['title']}")
                        st.write(f"Published: {video['published_at']}")
                        st.write(f"Description: {video['description']}")
                        st.write('---')
                    
                    st.subheader('Digital Product Recommendations')
                    with st.spinner('Generating recommendations...'):
                        recommendations = get_product_recommendations(info, openai_api_key, 'youtube')
                        st.write(recommendations)
                else:
                    st.error(info)
                    
            # Display Unsplash images for each product recommendation
            def display_product_images(recommendations):
                # Parse recommendations to extract image keywords
                import re
                products = re.split(r'Product \d+:', recommendations)[1:]
                st.subheader('Product Visualizations')
                for i, product in enumerate(products, 1):
                    # Extract product category and image keywords
                    category_match = re.search(r'Category: \[([^\]]+)\]', product)
                    keywords_match = re.search(r'Image Keywords: \[([^\]]+)\]', product)
                    
                    if category_match and keywords_match:
                        category = category_match.group(1)
                        keywords = keywords_match.group(1)
                        
                        # Create a column layout for each product
                        col1, col2 = st.columns([1, 2])
                        with col1:
                            st.write(f"Product {i}: {category}")
                        
                        with col2:
                            # Get Unsplash images for the keywords
                            images = get_unsplash_images(keywords, count=1)
                            if images:
                                st.image(images[0], caption=f"Visualization for {category}", use_column_width=True)
                            else:
                                st.warning(f"No visualization available for {category}")
                        
                        st.markdown("---")
            # Add image display to both Instagram and YouTube sections
            st.subheader('Digital Product Recommendations with Visuals')
            with st.spinner('Generating recommendations and finding relevant images...'):
                recommendations = get_product_recommendations(info, openai_api_key, platform.lower())
                st.write(recommendations)
                display_product_images(recommendations)

    else:
        st.error(f'Please enter a valid {platform} profile URL')

# Add usage instructions
st.markdown('''
### Instructions:
1. Select the social media platform you want to analyze
2. Enter your OpenAI API key to enable AI-powered product recommendations
3. Paste the profile URL
4. Click 'Analyze Profile' to get detailed insights

**Note:** 
- For Instagram private profiles, only basic public information will be available
- Product recommendations are available for all social media platforms when an OpenAI API key is provided
''')