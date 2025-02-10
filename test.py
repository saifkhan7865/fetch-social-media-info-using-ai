import os
from isodate import parse_duration
from googleapiclient.discovery import build
import requests
from unsplash.api import Api
from unsplash.auth import Auth
import instaloader
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
            # Try legacy lookup using forUsername (may fail for custom handles)
            request = youtube.channels().list(
                part='id',
                forHandle='@'+username
            )
            response = request.execute()
        
            if response.get('items'):
                channel_id = response['items'][0]['id']
            else:
                
                youtube_channel_info = youtube.channels().list(
                    part= 'snippet',
                    forHandle=channel_id
                )
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
        elif 'user/' in channel_url:
            # Legacy format using /user/username
            username = channel_url.split('user/')[1].split('/')[0]
            request = youtube.channels().list(
                part='id',
                forUsername=username
            )
            response = request.execute()
            if response.get('items'):
                channel_id = response['items'][0]['id']
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
        video_ids = [video['id']['videoId'] for video in videos_response['items'] if 'videoId' in video['id']]
        
        # Fetch video details (contentDetails contains the duration)
        if video_ids:
            videos_details_request = youtube.videos().list(
                part='contentDetails',
                id=','.join(video_ids)
            )
            videos_details_response = videos_details_request.execute()
            
            # Analyze video durations
            video_types = {'shorts': 0, 'regular': 0}
            for video in videos_details_response.get('items', []):
                duration_iso = video['contentDetails']['duration']
                duration_seconds = int(parse_duration(duration_iso).total_seconds())
                if duration_seconds < 60:
                    video_types['shorts'] += 1
                else:
                    video_types['regular'] += 1
        else:
            video_types = {'shorts': 0, 'regular': 0}
        
        return {
            'channel_name': channel_info['snippet']['title'],
            'description': channel_info['snippet']['description'],
            'subscriber_count': int(channel_info['statistics']['subscriberCount']),
            'video_count': int(channel_info['statistics']['videoCount']),
            'view_count': int(channel_info['statistics']['viewCount']),
            'video_types': video_types
        }
    except Exception as e:
        return f"Error fetching YouTube channel: {str(e)}"


L = instaloader.Instaloader()
async def get_tiktok_info(username):
    try:
        async with TikTokApi() as api:
            user = await api.user(username)
            user_info = await user.info()
            
            if not user_info:
                return f"Could not fetch TikTok profile for {username}"

            return {
                'username': user_info.get('uniqueId', 'N/A'),
                'nickname': user_info.get('nickname', 'N/A'),
                'followers': user_info.get('followerCount', 'N/A'),
                'following': user_info.get('followingCount', 'N/A'),
                'total_likes': user_info.get('heartCount', 'N/A'),
                'video_count': user_info.get('videoCount', 'N/A'),
                'avg_engagement': 'Not calculated',
            }
    except Exception as e:
        return f"Error fetching TikTok profile: {str(e)}"
# Example usage:

def get_instagram_info(username):
    try:
        # Remove '@' if present
        username = username.strip('@')
        
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


if __name__ == "__main__":
    # Replace with your channel URL, e.g. a custom handle URL:
    channel_url = "https://www.youtube.com/@mohammed.khan07"
    # Create an event loop and run the async function
    get_instagram_info("@saif.khan__")
