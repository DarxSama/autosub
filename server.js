const express = require('express');
const ffmpeg = require('fluent-ffmpeg');
const fs = require('fs');
const mysql = require('mysql2')
const axios = require('axios'); // ใช้สำหรับการส่งไฟล์ไปยัง API
const app = express();
const port = 4000;

const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const SECRET_KEY = 'UX23Y24%@&2aMb';

// Load SSL certificates
const privateKey = fs.readFileSync('privatekey.pem', 'utf8');
const certificate = fs.readFileSync('certificate.pem', 'utf8');
const credentials = { key: privateKey, cert: certificate };
// Import CORS library
const cors = require('cors');

//Database(MySql) configulation
const db = mysql.createConnection(
    {
        host: "localhost",
        user: "root",
        password: "1234",
        database: "shopdee"
    }
)
db.connect()
// ฟังก์ชันช่วยสำหรับ query ฐานข้อมูล
const query = (sql, params) => {
  return new Promise((resolve, reject) => {
      db.query(sql, params, (err, results) => {
          if (err) return reject(err);
          resolve(results);
      });
  });
};

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// API สำหรับดึงวิดีโอ
app.get('/get-video', (req, res) => {
  const filePath = 'C:\\Users\\lnoon\\OneDrive\\Desktop\\AutoSubtitle_Project_11.11\\AutoSubtitle_Project\\Api_AutoSubtitle\\input.mp4';

  if (!fs.existsSync(filePath)) {
    console.error('ไฟล์ไม่พบ:', filePath);
    return res.status(404).send('ไฟล์ไม่พบ');
  }

  const stat = fs.statSync(filePath);
  const fileSize = stat.size;
  const range = req.headers.range;

  if (range) {
    const parts = range.replace(/bytes=/, "").split("-");
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;

    if (start >= fileSize) {
      res.status(416).send('Requested range not satisfiable\n' + start + ' >= ' + fileSize);
      return;
    }

    const chunksize = (end - start) + 1;
    const file = fs.createReadStream(filePath, { start, end });
    const head = {
      'Content-Range': `bytes ${start}-${end}/${fileSize}`,
      'Accept-Ranges': 'bytes',
      'Content-Length': chunksize,
      'Content-Type': 'video/mp4',
    };

    console.log(`Request range: ${range}`);
    res.writeHead(206, head);
    file.pipe(res);
  } else {
    const head = {
      'Content-Length': fileSize,
      'Content-Type': 'video/mp4',
    };
    console.log('Streaming full video');
    res.writeHead(200, head);
    fs.createReadStream(filePath).pipe(res);
  }
});

// Register
app.post('/api/register', 
  function(req, res) {  
      const { username, password, firstName, lastName } = req.body;
      
      //check existing username
      let sql="SELECT * FROM customer WHERE username=?";
      db.query(sql, [username], async function(err, results) {
          if (err) throw err;
          
          if(results.length == 0) {
              //password and salt are encrypted by hash function (bcrypt)
              const salt = await bcrypt.genSalt(10); //generate salte
              const password_hash = await bcrypt.hash(password, salt);        
                              
              //insert customer data into the database
              sql = 'INSERT INTO customer (username, password, firstName, lastName) VALUES (?, ?, 0, 0)';
                db.query(sql, [username, password_hash, firstName, lastName], (err, result) => {
                  if (err) throw err;
              
                  res.send({'message':'ลงทะเบียนสำเร็จแล้ว','status':true});
              });      
          }else{
              res.send({'message':'ชื่อผู้ใช้ซ้ำ','status':false});
          }

      });      
  }
);
//Login
app.post('/api/login',
  async function(req, res){
      //Validate username
      const {username, password} = req.body;                
      let sql = "SELECT * FROM customer WHERE username=? AND isActive = 1";        
      let customer = await query(sql, [username, username]);        
      
      if(customer.length <= 0){            
          return res.send( {'message':'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง','status':false} );
      }else{            
          customer = customer[0];
          custID = customer['custID'];               
          password_hash = customer['password'];       
      }

      //validate a number of attempts 
      let loginAttempt = 0;
      sql = "SELECT loginAttempt FROM customer WHERE username=? AND isActive = 1 ";        
      sql += "AND lastAttemptTime >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR ";        
      
      row = await query(sql, [username, username]);    
      if(row.length > 0){
          loginAttempt = row[0]['loginAttempt'];

          if(loginAttempt>= 3) {
              return res.send( {'message':'บัญชีคุณถูกล๊อก เนื่องจากมีการพยายามเข้าสู่ระบบเกินกำหนด','status':false} );    
          }    
      }else{
          //reset login attempt                
          sql = "UPDATE customer SET loginAttempt = 0, lastAttemptTime=NULL WHERE username=? AND isActive = 1";                    
          await query(sql, [username, username]);               
      }              
      

      //validate password       
      if(bcrypt.compareSync(password, password_hash)){
          //reset login attempt                
          sql = "UPDATE customer SET loginAttempt = 0, lastAttemptTime=NULL WHERE username=? AND isActive = 1";        
          await query(sql, [username, username]);   

          //get token
          const token = jwt.sign({ custID: custID, username: username }, SECRET_KEY, { expiresIn: '1h' });                

          customer['token'] = token;
          customer['message'] = 'เข้าสู่ระบบสำเร็จ';
          customer['status'] = true;

          res.send(customer);            
      }else{
          //update login attempt
          const lastAttemptTime = new Date();
          sql = "UPDATE customer SET loginAttempt = loginAttempt + 1, lastAttemptTime=? ";
          sql += "WHERE username=? AND isActive = 1";                   
          await query(sql, [lastAttemptTime, username, username]);           
          
          if(loginAttempt >=2){
              res.send( {'message':'บัญชีคุณถูกล๊อก เนื่องจากมีการพยายามเข้าสู่ระบบเกินกำหนด','status':false} );    
          }else{
              res.send( {'message':'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง','status':false} );    
          }            
      }

  }
);

app.listen(port, () => {
  console.log(`เซิร์ฟเวอร์ทำงานที่ http://localhost:${port}`);
});
