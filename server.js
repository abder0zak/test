const express = require('express');
const path = require('path');
const multer = require('multer');
const fs = require('fs');
const cloudinary = require('cloudinary').v2;
const streamifier = require('streamifier');
let db; // Will be either MongoDB collection or NeDB instance
let useMongoDB = false;
let useCloudinary = false;

// MongoDB setup
const { MongoClient, ObjectId } = require('mongodb');
// NeDB setup (fallback)
const Datastore = require('nedb-promises');

const app = express();
const PORT = process.env.PORT || 3000;
const ADMIN_SECRET = process.env.ADMIN_SECRET || "Maison2026";

// Check if we should use MongoDB
if (process.env.MONGODB_URI) {
  useMongoDB = true;
  console.log('Attempting to connect to MongoDB Atlas...');
} else {
  console.warn('MONGODB_URI not set - falling back to local NeDB database');
}

// Check if we should use Cloudinary
if (process.env.CLOUDINARY_CLOUD_NAME &&
    process.env.CLOUDINARY_API_KEY &&
    process.env.CLOUDINARY_API_SECRET) {
  useCloudinary = true;
  cloudinary.config({
    cloud_name: process.env.CLOUDINARY_CLOUD_NAME,
    api_key: process.env.CLOUDINARY_API_KEY,
    api_secret: process.env.CLOUDINARY_API_SECRET
  });
  console.log('Cloudinary configured for image uploads');
} else {
  console.warn('Cloudinary credentials not complete - falling back to local file storage for uploads');
}

// Initialize database
async function initDatabase() {
  if (useMongoDB) {
    try {
      const client = new MongoClient(process.env.MONGODB_URI);
      await client.connect();
      db = client.db('pastryDB');
      console.log('Connected to MongoDB Atlas');
      return true;
    } catch (err) {
      console.error('MongoDB connection failed:', err.message);
      console.warn('Falling back to local NeDB database');
      useMongoDB = false;
    }
  }

  // Use NeDB as fallback
  if (!useMongoDB) {
    db = Datastore.create({ filename: 'pastries.db', autoload: true });
    console.log('Using local NeDB database');
    return true;
  }
}

// Initialize storage for uploads
const uploadDir = path.join(__dirname, 'public', 'uploads');
if (!fs.existsSync(uploadDir)){
  fs.mkdirSync(uploadDir, { recursive: true });
}

let upload;
if (useCloudinary) {
  // Use memory storage for streaming to Cloudinary
  const storage = multer.memoryStorage();
  upload = multer({ storage: storage });
} else {
  // Use disk storage for local files
  const storage = multer.diskStorage({
    destination: (req, file, cb) => cb(null, uploadDir),
    filename: (req, file, cb) => {
      const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
      cb(null, uniqueSuffix + path.extname(file.originalname));
    }
  });
  upload = multer({ storage: storage });
}

// Seed database with initial items if empty
const seedData = async () => {
  try {
    let count = 0;
    if (useMongoDB) {
      count = await db.collection('pastries').countDocuments();
    } else {
      count = await db.count({});
    }

    if (count === 0) {
      const initialData = [
        { name: "Almond Croissant", price: "4.75", status: "Freshly Baked", image: "https://images.unsplash.com/photo-1555507036-ab1f4038808a?auto=format&fit=crop&w=400&q=80" },
        { name: "Raspberry Tart", price: "6.20", status: "Only 3 Left!", image: "https://images.unsplash.com/photo-1587314168485-3236d6710814?auto=format&fit=crop&w=400&q=80" }
      ];

      if (useMongoDB) {
        await db.collection('pastries').insertMany(initialData);
      } else {
        await db.insert(initialData);
      }
      console.log("Database seeded with baseline pastries!");
    }
  } catch (err) {
    console.error('Error seeding database:', err);
  }
};

// Middleware to ensure DB is initialized
app.use(async (req, res, next) => {
  if (!db) {
    await initDatabase();
    await seedData();
  }
  next();
});

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Security gate check middleware
function authorizeAdmin(req, res, next) {
    const userSecret = req.headers['x-admin-secret'];
    if (userSecret === ADMIN_SECRET) {
        next();
    } else {
        res.status(401).json({ error: "Invalid Admin Passcode. Access Denied." });
    }
}

// API: Get all pastries
app.get('/api/pastries', async (req, res) => {
    try {
        let pastries;
        if (useMongoDB) {
            pastries = await db.collection('pastries').find({}).toArray();
        } else {
            pastries = await db.find({});
        }
        res.json(pastries);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// API: Add a new pastry item (Admin)
app.post('/api/pastries', authorizeAdmin, upload.single('imageFile'), async (req, res) => {
    try {
        const { name, price, status } = req.body;
        if (!name || !price) return res.status(400).json({ error: "Missing required fields" });

        // Handle image upload
        let imageLocation = "https://placehold.co/400x300/f5f5f4/a8a29e?text=No+Photo";
        if (req.file) {
          if (useCloudinary) {
            // Upload to Cloudinary
            const uploadResponse = await new Promise((resolve, reject) => {
                const uploadStream = cloudinary.uploader.upload_stream(
                    { folder: 'pastries' },
                    (error, result) => {
                        if (error) reject(error);
                        else resolve(result);
                    }
                );
                streamifier.createReadStream(req.file.buffer).pipe(uploadStream);
            });
            imageLocation = uploadResponse.secure_url;
          } else {
            // Save locally
            imageLocation = `/uploads/${req.file.filename}`;
          }
        }

        const newItem = {
            name,
            price,
            status: status || "Freshly Baked",
            image: imageLocation,
            createdAt: new Date()
        };

        let result;
        if (useMongoDB) {
            result = await db.collection('pastries').insertOne(newItem);
            newItem._id = result.insertedId;
        } else {
            result = await db.insert(newItem);
            newItem._id = result._id;
        }
        res.status(201).json(newItem);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// API: Delete a pastry item (Admin)
app.delete('/api/pastries/:id', authorizeAdmin, async (req, res) => {
    try {
        const itemId = req.params.id;

        // Special case for auth test endpoint
        if (itemId === 'test_auth_id') {
            return res.status(200).json({ success: true, message: "Auth successful" });
        }

        // Locate the item first
        let item;
        if (useMongoDB) {
            let queryId;
            try {
                queryId = new ObjectId(itemId);
            } catch (err) {
                queryId = itemId;
            }
            item = await db.collection('pastries').findOne({ _id: queryId });
        } else {
            item = await db.findOne({ _id: itemId });
        }

        // Delete image if needed
        if (item && item.image) {
          if (useCloudinary && item.image.includes('cloudinary.com')) {
            // Extract public ID from Cloudinary URL to delete
            const urlParts = item.image.split('/');
            const publicIdWithExtension = urlParts.slice(-2).join('/');
            const publicId = publicIdWithExtension.split('.')[0];
            await cloudinary.uploader.destroy(`pastries/${publicId}`);
          } else if (!useCloudinary && item.image.startsWith('/uploads/')) {
            // Delete local file
            const fullPath = path.join(__dirname, 'public', item.image);
            if (fs.existsSync(fullPath)) fs.unlinkSync(fullPath);
          }
        }

        // Delete from database
        let result;
        if (useMongoDB) {
            let queryId;
            try {
                queryId = new ObjectId(itemId);
            } catch (err) {
                queryId = itemId;
            }
            result = await db.collection('pastries').deleteOne({ _id: queryId });
        } else {
            result = await db.remove({ _id: itemId }, {});
        }

        if (useMongoDB ? result.deletedCount === 0 : result === 0) {
            return res.status(404).json({ error: "Item not found" });
        }
        res.json({ success: true, message: "Item removed" });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Export the app for Vercel
module.exports = app;

// Local development server
if (process.env.NODE_ENV !== 'production') {
    const startServer = async () => {
      try {
        await initDatabase();
        await seedData();
        app.listen(PORT, () => console.log(`🚀 Patisserie Server running at http://localhost:${PORT}`));
      } catch (err) {
        console.error('Failed to start server:', err);
        process.exit(1);
      }
    };

    startServer();
}