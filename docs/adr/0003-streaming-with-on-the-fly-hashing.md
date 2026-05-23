# Streaming Uploads with On-the-fly Hashing

Files will be encrypted and uploaded as a stream rather than using temporary local files. To ensure data integrity without persisting the ciphertext to disk, the CLI will calculate the hash of the encrypted stream during upload and verify it against the hash returned by the Hippius server.