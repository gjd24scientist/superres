import tensorflow as tf
import glob
import argparse
import logging
import os
import sys
import config as cfg

from blocks import relu_block, res_block, deconv_block, conv_block, dense_block

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)

# TODO Download all images
# TODO Start making hyperparameters command line options
# TODO Check that things work
# TODO Check that things match with paper

class Loader(object):
    def __init__(self, images):
        cfg.NUM_IMAGES = len(images)
        cfg.NUM_TRAIN_IMAGES = int(cfg.NUM_IMAGES * cfg.TRAIN_RATIO)
        cfg.NUM_VAL_IMAGES = int(cfg.NUM_IMAGES * cfg.VAL_RATIO)
        train_images = images[:cfg.NUM_TRAIN_IMAGES]
        val_images = images[cfg.NUM_TRAIN_IMAGES:cfg.NUM_TRAIN_IMAGES + cfg.NUM_VAL_IMAGES]
        test_images = images[cfg.NUM_TRAIN_IMAGES + cfg.NUM_VAL_IMAGES:]

        self.q_train = tf.train.string_input_producer(train_images)
        self.q_val = tf.train.string_input_producer(val_images)
        self.q_test = tf.train.string_input_producer(test_images)
        cfg.NUM_TRAIN_BATCHES = len(train_images) // cfg.BATCH_SIZE
        cfg.NUM_VAL_BATCHES = len(val_images) // cfg.BATCH_SIZE
        cfg.NUM_TEST_BATCHES = len(test_images) // cfg.BATCH_SIZE

        logging.info("Running on %d images" % (cfg.NUM_IMAGES,))

    def _get_pipeline(self, q):
        reader = tf.WholeFileReader()
        key, value = reader.read(q)
        raw_img = tf.image.decode_jpeg(value, channels=cfg.NUM_CHANNELS)
        my_img = tf.image.per_image_whitening(raw_img)
        my_img = tf.random_crop(my_img, [cfg.HR_HEIGHT, cfg.HR_WIDTH, cfg.NUM_CHANNELS],
                seed=cfg.RANDOM_SEED)
        min_after_dequeue = 1
        capacity = min_after_dequeue + 3 * cfg.BATCH_SIZE
        batch = tf.train.shuffle_batch([my_img], batch_size=cfg.BATCH_SIZE, capacity=capacity,
                min_after_dequeue=min_after_dequeue, seed=cfg.RANDOM_SEED)
        small_batch = tf.image.resize_bicubic(batch, [cfg.LR_HEIGHT, cfg.LR_WIDTH])
        return (small_batch, batch)

    def batch(self):
        return (self._get_pipeline(self.q_train),
                self._get_pipeline(self.q_val),
                self._get_pipeline(self.q_test))

class GAN(object):
    def __init__(self):
        self.g_images = tf.placeholder(tf.float32, 
            [cfg.BATCH_SIZE, cfg.LR_HEIGHT, cfg.LR_WIDTH, cfg.NUM_CHANNELS])
        self.d_images = tf.placeholder(tf.float32,
            [cfg.BATCH_SIZE, cfg.HR_HEIGHT, cfg.HR_WIDTH, cfg.NUM_CHANNELS])
        self.is_training = tf.placeholder(tf.bool, [1])

    def build_model(self):
        with tf.variable_scope("G"):
            self.G = self.generator()

        with tf.variable_scope("D") as scope:
            self.D = self.discriminator(self.d_images)
            scope.reuse_variables()
            self.DG = self.discriminator(self.G)

        # MSE Loss and Adversarial Loss for G
        self.mse_loss = tf.reduce_mean(tf.squared_difference(self.d_images, self.G))
        self.g_ad_loss = tf.reduce_mean(tf.neg(tf.log(self.DG)))

        self.g_loss = self.mse_loss + 0.001 * self.g_ad_loss
        tf.scalar_summary('g_loss', self.g_loss)

        # Real Loss and Adversarial Loss for D
        self.d_loss_real = tf.reduce_mean(tf.neg(tf.log(self.D)))
        self.d_loss_fake = tf.reduce_mean(tf.log(self.DG))

        self.d_loss = self.d_loss_real + self.d_loss_fake
        tf.scalar_summary('d_loss', self.d_loss)

        t_vars = tf.trainable_variables()

        self.d_vars = [var for var in t_vars if 'D/' in var.name]
        self.g_vars = [var for var in t_vars if 'G/' in var.name]

        # TODO Missing VGG loss and regularization loss. 
        # Also missing weighting on losses.

    def generator(self):
        """Returns model generator, which is a DeConvNet.
        Assumed properties:
            gen_input - a scalar
            batch_size
            dimensions of filters and other hyperparameters.
            ...
        """
        with tf.variable_scope("conv1"):
            h = conv_block(self.g_images, relu=True)

        for i in range(1, 17):
            with tf.variable_scope("res" + str(i)):
                h = res_block(h, self.is_training)

        with tf.variable_scope("deconv1"):
            h = deconv_block(h)

        with tf.variable_scope("deconv2"):
            h = deconv_block(h)

        with tf.variable_scope("conv2"):
            h = conv_block(h, output_channels=3)

        return h

    def discriminator(self, inp):
        """Returns model discriminator.
        Assumed properties:
            disc_input - an image tensor
            G - a generator
            ...
        """
        with tf.variable_scope("conv1"):
            h = conv_block(inp, leaky_relu=True)

        with tf.variable_scope("conv2"):
            h = conv_block(h, leaky_relu=True, bn=True, 
                is_training_cond=self.is_training, stride=2)

        with tf.variable_scope("conv3"):
            h = conv_block(h, leaky_relu=True, bn=True, 
                is_training_cond=self.is_training, output_channels=128)

        with tf.variable_scope("conv4"):
            h = conv_block(h, leaky_relu=True, bn=True,
                is_training_cond=self.is_training, output_channels=128, stride=2)

        with tf.variable_scope("conv5"):
            h = conv_block(h, leaky_relu=True, bn=True,
                is_training_cond=self.is_training, output_channels=256, stride=1)

        with tf.variable_scope("conv6"):
            h = conv_block(h, leaky_relu=True, bn=True,
                is_training_cond=self.is_training, output_channels=256, stride=2)

        with tf.variable_scope("conv7"):
            h = conv_block(h, leaky_relu=True, bn=True,
                is_training_cond=self.is_training, output_channels=512, stride=1)

        with tf.variable_scope("conv8"):
            h = conv_block(h, leaky_relu=True, bn=True,
                is_training_cond=self.is_training, output_channels=512, stride=2)

        with tf.variable_scope("dense1"):
            h = dense_block(h, leaky_relu=True, output_size=1024)

        with tf.variable_scope("dense2"):
            h = dense_block(h, sigmoid=True, output_size=1)

        return h


class SuperRes(object):
    def __init__(self, sess, loader):
        logging.info("Building Model.")
        self.sess = sess
        self.loader = loader
        self.train_batch, self.val_batch, self.test_batch = loader.batch()

        self.GAN = GAN()
        self.GAN.build_model()

        self.g_mse_optim = (tf.train.AdamOptimizer(cfg.LEARNING_RATE, beta1=cfg.BETA_1)
            .minimize(self.GAN.mse_loss, var_list=self.GAN.g_vars))
        self.d_optim = (tf.train.AdamOptimizer(cfg.LEARNING_RATE, beta1=cfg.BETA_1)
            .minimize(self.GAN.d_loss, var_list=self.GAN.d_vars))
        self.g_optim = (tf.train.AdamOptimizer(cfg.LEARNING_RATE, beta1=cfg.BETA_1)
            .minimize(self.GAN.g_loss, var_list=self.GAN.g_vars))

    def _pretrain(self):
        lr, hr = self.sess.run(self.train_batch)
        summary, _, loss = self.sess.run(
            [self.merged, self.g_mse_optim, self.GAN.mse_loss],
            feed_dict={
                self.GAN.g_images: lr,
                self.GAN.d_images: hr,
                self.GAN.is_training: [True]
        })
        return summary, loss

    def _train(self):
        """
        Returns (summary, mse_loss, g_ad_loss, g_loss, d_loss_real, d_loss_fake, d_loss)
        """
        lr, hr = sess.run(self.val_batch)
        res = sess.run(
            [self.merged, self.d_optim, self.g_optim, self.mse_loss, self.g_ad_loss,
             self.g_loss, self.d_loss_real, self.d_loss_fake, self.d_loss],
            feed_dict={
                self.GAN.g_images: lr,
                self.GAN.d_images: hr,
                self.GAN.is_training: [True]
        })

        return res[0] + res[3:]

    def _val(self):
        """
        Returns (summary, mse_loss, g_ad_loss, g_loss, d_loss_real, d_loss_fake, d_loss)
        """
        lr, hr = sess.run(self.train_batch)
        res = sess.run(
            [self.merged, self.mse_loss, self.g_ad_loss,
             self.g_loss, self.d_loss_real, self.d_loss_fake, self.d_loss],
            feed_dict={
                self.GAN.g_images: lr,
                self.GAN.d_images: hr,
                self.GAN.is_training: [False]
        })

        return res

    def _test(self):
        """
        Returns (summary, mse_loss, g_ad_loss, g_loss, d_loss_real, d_loss_fake, d_loss)
        """
        lr, hr = sess.run(self.test_batch)
        res = sess.run(
            [self.merged, self.d_optim, self.g_optim, self.mse_loss, self.g_ad_loss,
             self.g_loss, self.d_loss_real, self.d_loss_fake, self.d_loss],
            feed_dict={
                self.GAN.g_images: lr,
                self.GAN.d_images: hr,
                self.GAN.is_training: [False]
        })

        return res[0] + res[3:]

    def _print_losses(self, losses, count):
        avg_losses = [x / count for x in losses]
        logging.info("G Loss: %f, MSE Loss: %d, Ad Loss: %d"
                % (avg_losses[0], avg_losses[1], avg_losses[2]))
        logging.info("D Loss: %f, Real Loss: %f, Fake Loss: %f"
                % (avg_losses[3], avg_losses[4], avg_losses[5]))

    def train_model(self):
        self.merged = tf.merge_all_summaries()
        self.pre_train_writer = tf.train.SummaryWriter(os.path.join(cfg.LOGS_DIR, 'pretrain'),
                self.sess.graph)
        self.train_writer = tf.train.SummaryWriter(os.path.join(cfg.LOGS_DIR, 'train'),
                self.sess.graph)
        self.val_writer = tf.train.SummaryWriter(os.path.join(cfg.LOGS_DIR, 'val'),
                self.sess.graph)
        saver = tf.train.Saver()

        with self.sess as sess:
            if cfg.USE_CHECKPOINT and os.path.isfile(cfg.CHECKPOINT):
                logging.info("Restoring saved parameters")
                saver.restore(sess, cfg.CHECKPOINT)
            else:
                logging.info("Initializing parameters")
                sess.run(tf.initialize_all_variables())

            coord = tf.train.Coordinator()
            threads = tf.train.start_queue_runners(coord=coord)

            # Pretrain
            logging.info("Begin Pre-Training")
            ind = 0
            for epoch in range(cfg.NUM_PRETRAIN_EPOCHS):
                logging.info("Pre-Training Epoch: %d" % (epoch,))
                loss_sum = 0
                for batch in range(cfg.NUM_TRAIN_BATCHES):
                    summary, loss = self._pretrain()
                    self.pre_train_writer.add_summary(summary, ind)
                    loss_sum += loss

                    if ind % 1000 == 0:
                        saver.save(sess, cfg.CHECKPOINT)
                        logging.info("Pre-Training Iter: %d" % (ind,))
                        logging.info("MSE Loss: %f" % (loss_sum / (batch + 1),))

                    ind += 1
                logging.info("Epoch MSE Loss: %f" % (loss_sum / cfg.NUM_TRAIN_BATCHES,))

            logging.info("Begin Training")
            # Train
            ind = 0
            for epoch in range(cfg.NUM_TRAIN_EPOCHS):
                logging.info("Training Epoch: %d" % (epoch,))
                losses = [0 for _ in range(6)]
                for batch in range(cfg.NUM_TRAIN_BATCHES):
                    res = self._train()
                    self.train_writer.add_summary(res[0], ind)
                    losses = [x + y for x, y in zip(losses, res[1:])]

                    if ind % 1000 == 0:
                        saver.save(sess, cfg.CHECKPOINT)
                        logging.info("Training Iter: %d" % (ind,))
                        self._print_losses(losses, batch + 1)

                    ind += 1

                logging.info("Epoch Training Losses")
                self._print_losses(losses, cfg.NUM_TRAIN_BATCHES)
                
                losses = [0 for _ in range(6)]
                for batch in range(cfg.NUM_VAL_BATCHES):
                    res = self._val()
                    self.val_writer.add_summary(res[0], ind)
                    losses = [x + y for x, y in zip(losses, res[1:])]
                    ind += 1

                logging.info("Epoch Validation Losses")
                self._print_losses(losses, cfg.NUM_VAL_BATCHES)

            coord.request_stop()
            coord.join(threads)

    def test_model(self):
        val_writer = tf.train.SummaryWriter(join(cfg.LOGS_DIR, 'test'), self.sess.graph)

        with self.sess as sess:
            logging.info("Begin Testing")
            # Test
            coord = tf.train.Coordinator()
            threads = tf.train.start_queue_runners(coord=coord)
            ind = 0
            for batch in range(cfg.NUM_TEST_BATCHES):
                lr, hr = sess.run(self.test_batch)
                res = self._test()
                test_writer.add_summary(res[0], ind)
                losses = [x + y for x, y in zip(losses, res[1:])]
                ind += 1

            logging.info("Test Losses")
            self._print_losses(losses, cfg.NUM_TEST_BATCHES)

            coord.request_stop()
            coord.join(threads)

def main():
    sess = tf.Session()
    file_list = glob.glob(cfg.IMAGES)
    loader = Loader(file_list)
    model = SuperRes(sess, loader)
    model.train_model()

    sess.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    main()
