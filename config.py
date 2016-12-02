IMAGES = "/home/images/imagenet/*.JPEG"
LOGS_DIR = "logs/"
CHECKPOINT = "checkpoint/weights"
USE_CHECKPOINT = False

HR_HEIGHT = 96
HR_WIDTH = 96
r = 4
LR_HEIGHT = HR_HEIGHT // r
LR_WIDTH = HR_WIDTH // r
NUM_CHANNELS = 3
BATCH_SIZE = 24
NUM_PRETRAIN_EPOCHS = 120
NUM_TRAIN_EPOCHS = 20
TRAIN_RATIO = .7
VAL_RATIO = .2

LEARNING_RATE = 1e-4
BN_EPSILON = 0.001
MOVING_AVERAGE_DECAY = 0.9997
BN_DECAY = MOVING_AVERAGE_DECAY
UPDATE_OPS_COLLECTION = 'update_ops'
BETA_1 = 0.9
RANDOM_SEED = 1337 

