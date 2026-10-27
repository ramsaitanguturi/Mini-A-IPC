// SPDX-License-Identifier: GPL-2.0
/* Mini A-IPC: bounded kernel-space byte-stream mailbox for Linux. */
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/fs.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/poll.h>
#include <linux/uaccess.h>
#include <linux/wait.h>
#include <linux/slab.h>

#define AIPC_DEVICE_NAME "aipc"
#define AIPC_DEFAULT_CAPACITY (64 * 1024)

static unsigned int capacity = AIPC_DEFAULT_CAPACITY;
module_param(capacity, uint, 0444);
MODULE_PARM_DESC(capacity, "Ring-buffer capacity in bytes (default 65536)");

struct aipc_device {
    unsigned char *buffer;
    size_t capacity;
    size_t head;
    size_t tail;
    size_t used;
    dev_t devno;
    struct cdev cdev;
    struct class *class;
    struct device *device;
    struct mutex lock;
    wait_queue_head_t readers;
    wait_queue_head_t writers;
};

static struct aipc_device *aipc;

static size_t ring_write(struct aipc_device *d, const unsigned char *src, size_t n)
{
    size_t first = min(n, d->capacity - d->tail);
    memcpy(d->buffer + d->tail, src, first);
    memcpy(d->buffer, src + first, n - first);
    d->tail = (d->tail + n) % d->capacity;
    d->used += n;
    return n;
}

static int aipc_open(struct inode *inode, struct file *file)
{
    (void)inode;
    (void)file;
    return 0;
}

static int aipc_release(struct inode *inode, struct file *file)
{
    (void)inode;
    (void)file;
    return 0;
}

static ssize_t aipc_read(struct file *file, char __user *out, size_t count, loff_t *offset)
{
    unsigned char *tmp;
    size_t n;
    ssize_t ret;
    (void)offset;
    if (!count) return 0;
    tmp = kmalloc(min_t(size_t, count, aipc->capacity), GFP_KERNEL);
    if (!tmp) return -ENOMEM;

    for (;;) {
        if (mutex_lock_interruptible(&aipc->lock)) { ret = -ERESTARTSYS; goto out; }
        if (aipc->used) {
            n = min(count, aipc->used);
            n = min(n, aipc->capacity);
            /*
             * Do not consume bytes until copy_to_user() succeeds. Keep the
             * mutex while copying so another reader cannot consume the same
             * bytes before this reader commits the head/used update.
             * copy_to_user() may fault/sleep; a mutex is sleepable.
             */
            {
                size_t first = min(n, aipc->capacity - aipc->head);
                unsigned long missing;
                memcpy(tmp, aipc->buffer + aipc->head, first);
                memcpy(tmp + first, aipc->buffer, n - first);
                missing = copy_to_user(out, tmp, n);
                if (missing) {
                    mutex_unlock(&aipc->lock);
                    ret = -EFAULT;
                    goto out;
                }
                aipc->head = (aipc->head + n) % aipc->capacity;
                aipc->used -= n;
            }
            mutex_unlock(&aipc->lock);
            wake_up_interruptible(&aipc->writers);
            ret = (ssize_t)n;
            goto out;
        }
        mutex_unlock(&aipc->lock);
        if (file->f_flags & O_NONBLOCK) { ret = -EAGAIN; goto out; }
        ret = wait_event_interruptible(aipc->readers, READ_ONCE(aipc->used) > 0);
        if (ret) { ret = -ERESTARTSYS; goto out; }
    }
out:
    kfree(tmp);
    return ret;
}

static ssize_t aipc_write(struct file *file, const char __user *in, size_t count, loff_t *offset)
{
    unsigned char *tmp;
    size_t done = 0;
    size_t chunk;
    ssize_t ret;
    (void)offset;
    if (!count) return 0;
    tmp = kmalloc(min_t(size_t, count, aipc->capacity), GFP_KERNEL);
    if (!tmp) return -ENOMEM;

    while (done < count) {
        chunk = min(count - done, aipc->capacity);
        if (copy_from_user(tmp, in + done, chunk)) { ret = done ? (ssize_t)done : -EFAULT; goto out; }
        for (;;) {
            if (mutex_lock_interruptible(&aipc->lock)) { ret = done ? (ssize_t)done : -ERESTARTSYS; goto out; }
            if (aipc->capacity > aipc->used) {
                size_t n = min(chunk, aipc->capacity - aipc->used);
                ring_write(aipc, tmp, n);
                mutex_unlock(&aipc->lock);
                done += n;
                wake_up_interruptible(&aipc->readers);
                break;
            }
            mutex_unlock(&aipc->lock);
            if (file->f_flags & O_NONBLOCK) { ret = done ? (ssize_t)done : -EAGAIN; goto out; }
            ret = wait_event_interruptible(aipc->writers, READ_ONCE(aipc->used) < aipc->capacity);
            if (ret) { ret = done ? (ssize_t)done : -ERESTARTSYS; goto out; }
        }
    }
    ret = (ssize_t)done;
out:
    kfree(tmp);
    return ret;
}

static __poll_t aipc_poll(struct file *file, poll_table *wait)
{
    __poll_t mask = 0;
    (void)file;
    poll_wait(file, &aipc->readers, wait);
    poll_wait(file, &aipc->writers, wait);
    if (READ_ONCE(aipc->used) > 0) mask |= EPOLLIN | EPOLLRDNORM;
    if (READ_ONCE(aipc->used) < aipc->capacity) mask |= EPOLLOUT | EPOLLWRNORM;
    return mask;
}

static const struct file_operations aipc_fops = {
    .owner = THIS_MODULE,
    .open = aipc_open,
    .release = aipc_release,
    .read = aipc_read,
    .write = aipc_write,
    .poll = aipc_poll,
    .llseek = no_llseek,
};

static int __init aipc_init(void)
{
    int ret;
    if (capacity < 2) return -EINVAL;
    aipc = kzalloc(sizeof(*aipc), GFP_KERNEL);
    if (!aipc) return -ENOMEM;
    aipc->capacity = capacity;
    aipc->buffer = kmalloc(aipc->capacity, GFP_KERNEL);
    if (!aipc->buffer) { ret = -ENOMEM; goto fail_device; }
    mutex_init(&aipc->lock);
    init_waitqueue_head(&aipc->readers);
    init_waitqueue_head(&aipc->writers);

    ret = alloc_chrdev_region(&aipc->devno, 0, 1, AIPC_DEVICE_NAME);
    if (ret) goto fail_buffer;
    cdev_init(&aipc->cdev, &aipc_fops);
    aipc->cdev.owner = THIS_MODULE;
    ret = cdev_add(&aipc->cdev, aipc->devno, 1);
    if (ret) goto fail_region;
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 4, 0)
    aipc->class = class_create(AIPC_DEVICE_NAME);
#else
    aipc->class = class_create(THIS_MODULE, AIPC_DEVICE_NAME);
#endif
    if (IS_ERR(aipc->class)) { ret = PTR_ERR(aipc->class); goto fail_cdev; }
    aipc->device = device_create(aipc->class, NULL, aipc->devno, NULL, AIPC_DEVICE_NAME);
    if (IS_ERR(aipc->device)) { ret = PTR_ERR(aipc->device); goto fail_class; }
    pr_info("mini_aipc: loaded /dev/%s capacity=%zu\n", AIPC_DEVICE_NAME, aipc->capacity);
    return 0;

fail_class:
    class_destroy(aipc->class);
fail_cdev:
    cdev_del(&aipc->cdev);
fail_region:
    unregister_chrdev_region(aipc->devno, 1);
fail_buffer:
    kfree(aipc->buffer);
fail_device:
    kfree(aipc);
    aipc = NULL;
    return ret;
}

static void __exit aipc_exit(void)
{
    if (!aipc) return;
    device_destroy(aipc->class, aipc->devno);
    class_destroy(aipc->class);
    cdev_del(&aipc->cdev);
    unregister_chrdev_region(aipc->devno, 1);
    wake_up_interruptible_all(&aipc->readers);
    wake_up_interruptible_all(&aipc->writers);
    kfree(aipc->buffer);
    kfree(aipc);
    aipc = NULL;
    pr_info("mini_aipc: unloaded\n");
}

module_init(aipc_init);
module_exit(aipc_exit);
MODULE_LICENSE("GPL");
MODULE_AUTHOR("Mini A-IPC project");
MODULE_DESCRIPTION("Bounded kernel-space IPC ring buffer character device");
MODULE_VERSION("0.1");
