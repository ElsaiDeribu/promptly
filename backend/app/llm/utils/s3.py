import os
from typing import List, Optional
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# ------------------------------------------------------------
# S3 Storage Wrapper
# ------------------------------------------------------------
class S3Wrapper:
    """Wrapper class for S3/MinIO operations to make it easy to swap implementations"""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: Optional[str] = None,
    ):
        """Initialize the S3 wrapper

        Args:
            bucket_name: Default bucket name (defaults to S3_BUCKET_NAME from env)
            endpoint_url: S3 endpoint URL (defaults to S3_ENDPOINT_URL from env)
            access_key: AWS access key (defaults to AWS_ACCESS_KEY_ID from env)
            secret_key: AWS secret key (defaults to AWS_SECRET_ACCESS_KEY from env)
            region: AWS region (defaults to AWS_REGION from env or "us-east-1")
        """
        # Get configuration from environment or use provided values
        self.bucket_name = bucket_name or os.getenv("S3_BUCKET_NAME")
        self.endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL")
        self.access_key = access_key or os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_key = secret_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")

        # Initialize S3 client
        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

    def upload_file(
        self, file_path: str, object_name: Optional[str] = None, bucket: Optional[str] = None
    ) -> bool:
        """
        Upload a file to S3 bucket.

        Args:
            file_path: Path to the file to upload
            object_name: S3 object name. If not specified, file_path basename is used
            bucket: Bucket name. If not specified, uses default bucket

        Returns:
            True if file was uploaded successfully, False otherwise
        """
        if object_name is None:
            object_name = os.path.basename(file_path)

        if bucket is None:
            bucket = self.bucket_name

        try:
            self.client.upload_file(file_path, bucket, object_name)
            print(f"Successfully uploaded {file_path} to {bucket}/{object_name}")
            return True
        except ClientError as e:
            print(f"Error uploading file: {e}")
            return False

    def put_file(
        self,
        data: bytes,
        object_name: str,
        bucket: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> bool:
        """
        Put file data (bytes) directly to S3 bucket.

        Args:
            data: File data as bytes to upload
            object_name: S3 object name
            bucket: Bucket name. If not specified, uses default bucket
            content_type: Content type (e.g., "image/jpeg", "application/pdf")

        Returns:
            True if file was uploaded successfully, False otherwise
        """
        if bucket is None:
            bucket = self.bucket_name

        try:
            kwargs = {"Body": data}
            if content_type:
                kwargs["ContentType"] = content_type

            self.client.put_object(Bucket=bucket, Key=object_name, **kwargs)
            print(f"Successfully put file data to {bucket}/{object_name}")
            return True
        except ClientError as e:
            print(f"Error putting file: {e}")
            return False

    


    def generate_presigned_url(
        self, object_name: str, expiration: int = 3600, bucket: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate a presigned URL for an S3 object.

        Args:
            object_name: S3 object name
            expiration: Time in seconds for the URL to remain valid (default: 1 hour)
            bucket: Bucket name. If not specified, uses default bucket

        Returns:
            Presigned URL as string, or None if error
        """
        if bucket is None:
            bucket = self.bucket_name

        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": object_name},
                ExpiresIn=expiration,
            )
            return url
        except ClientError as e:
            print(f"Error generating presigned URL: {e}")
            return None
