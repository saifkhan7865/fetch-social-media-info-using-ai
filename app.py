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

def process_social_media_url(url):
    if 'instagram.com' in url:
        username = url.split('instagram.com/')[1].split('/')[0]
        return username
    return None

def get_product_recommendations(profile_info, openai_api_key):
    try:
        if not openai_api_key:
            return "Please provide an OpenAI API key to get product recommendations."
        
        llm = ChatOpenAI(openai_api_key=openai_api_key, temperature=0.7, model_name="gpt-3.5-turbo")
        
        prompt = PromptTemplate(
            input_variables=["profile_info"],
            template="""Based on the following Instagram profile information, suggest 5 digital products that would be most suitable for this creator to sell to their audience. Consider their content type, engagement rate, and audience interests based on hashtags.

Profile Information:
{profile_info}

Provide 5 specific digital product recommendations, each with a brief explanation of why it would work well for this audience."""
        )
        
        chain = LLMChain(llm=llm, prompt=prompt)
        
        # Format profile info for the prompt
        profile_summary = f"""- Audience size: {profile_info['followers']} followers
- Content focus: Top hashtags include {', '.join(list(profile_info['top_hashtags'].keys())[:5])}
- Engagement rate: {profile_info['avg_engagement_rate']}%
- Content mix: {profile_info['post_types']['image']} images, {profile_info['post_types']['video']} videos
- Bio: {profile_info['bio']}"""
        
        recommendations = chain.run(profile_summary)
        return recommendations
    except Exception as e:
        return f"Error generating recommendations: {str(e)}"

# Streamlit UI
st.title('Instagram Profile Analyzer & Product Recommender')

# OpenAI API key input
openai_api_key = st.text_input('Enter your OpenAI API key:', type='password')

# Instagram URL input
instagram_url = st.text_input('Enter the Instagram profile URL:')

if st.button('Analyze Profile') and instagram_url:
    username = process_social_media_url(instagram_url)
    
    if username:
        with st.spinner('Fetching profile information...'):
            info = get_instagram_info(username)
            
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
                
                # Display post types
                st.write("Content Mix:")
                st.write(f"- Images: {info['post_types']['image']}")
                st.write(f"- Videos: {info['post_types']['video']}")
                
                # Display top hashtags
                st.subheader('Top Hashtags')
                for tag, count in info['top_hashtags'].items():
                    st.write(f"#{tag}: {count} posts")
                
                if openai_api_key:
                    st.subheader('Digital Product Recommendations')
                    with st.spinner('Generating recommendations...'):
                        recommendations = get_product_recommendations(info, openai_api_key)
                        st.write(recommendations)
                else:
                    st.warning('Please enter your OpenAI API key to get product recommendations.')
        else:
            st.error(info)
    else:
        st.error('Please enter a valid Instagram profile URL')

# Add usage instructions
st.markdown('''
### Instructions:
1. Enter your OpenAI API key to enable AI-powered product recommendations
2. Paste an Instagram profile URL
3. Click 'Analyze Profile' to get detailed profile insights and product suggestions

**Note:** For private profiles, only basic public information will be available.
''')