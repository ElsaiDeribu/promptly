import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


# ------------------------------------------------------------
# S3 Storage Wrapper
# ------------------------------------------------------------
class S3Wrapper:
    """Wrapper class for S3/MinIO operations to make it easy to swap implementations"""

    def __init__(
        self,
        bucket_name: str | None = None,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str | None = None,
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
        # Use a browser-accessible S3/MinIO endpoint for presigned URLs.
        # This cannot be an internal address like 'minio:9000' because browsers can't reach Docker-internal hosts.
        self.public_endpoint_url = os.getenv(
            "S3_PUBLIC_ENDPOINT_URL", self.endpoint_url,
        )

        config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        )
        # Initialize S3 client
        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=config,
        )

        # Separate client signed against the public endpoint, used only to
        # generate presigned URLs that the browser will call.
        if self.public_endpoint_url and self.public_endpoint_url != self.endpoint_url:
            self.presign_client = boto3.client(
                "s3",
                endpoint_url=self.public_endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                config=config,
            )
        else:
            self.presign_client = self.client

    def put_file(
        self,
        data: bytes,
        object_name: str,
        bucket: str | None = None,
        content_type: str | None = None,
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

    def get_file(self, object_name: str, bucket: str | None = None) -> bytes | None:
        """
        Download an object from S3 as bytes.

        Args:
            object_name: S3 object name
            bucket: Bucket name. If not specified, uses default bucket

        Returns:
            Object data as bytes, or None if error
        """
        if bucket is None:
            bucket = self.bucket_name

        try:
            response = self.client.get_object(Bucket=bucket, Key=object_name)
            return response["Body"].read()
        except ClientError as e:
            print(f"Error downloading file: {e}")
            return None

    def ensure_bucket(self, bucket: str | None = None) -> bool:
        """Create the bucket if it does not already exist.

        Returns:
            True if the bucket exists (or was created), False on error.
        """
        if bucket is None:
            bucket = self.bucket_name

        try:
            self.client.head_bucket(Bucket=bucket)
            return True
        except ClientError:
            try:
                self.client.create_bucket(Bucket=bucket)
                return True
            except ClientError as e:
                print(f"Error creating bucket: {e}")
                return False

    def object_exists(self, object_name: str, bucket: str | None = None) -> bool:
        """Return True if the object exists in the bucket."""
        if bucket is None:
            bucket = self.bucket_name

        try:
            self.client.head_object(Bucket=bucket, Key=object_name)
            return True
        except ClientError:
            return False

    def generate_presigned_upload_url(
        self,
        object_name: str,
        expiration: int = 3600,
        content_type: str | None = None,
        bucket: str | None = None,
    ) -> str | None:
        """Generate a presigned URL the browser can PUT a file to directly.

        The returned URL is signed against the public endpoint so it is
        reachable from the browser (not the internal docker hostname).

        Args:
            object_name: S3 object key the file will be stored under
            expiration: Time in seconds the URL stays valid (default: 1 hour)
            content_type: Content type the client must send with the PUT
            bucket: Bucket name. If not specified, uses default bucket

        Returns:
            Presigned PUT URL as string, or None if error
        """
        if bucket is None:
            bucket = self.bucket_name

        params = {"Bucket": bucket, "Key": object_name}
        if content_type:
            params["ContentType"] = content_type

        try:
            return self.presign_client.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=expiration,
            )
        except ClientError as e:
            print(f"Error generating presigned upload URL: {e}")
            return None

    def generate_presigned_url(
        self, object_name: str, expiration: int = 3600, bucket: str | None = None,
    ) -> str | None:
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
            url = self.presign_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": object_name},
                ExpiresIn=expiration,
            )
            return url
        except ClientError as e:
            print(f"Error generating presigned URL: {e}")
            return None
