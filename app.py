import os
from datetime import datetime

import discord
from discord.ext import commands
from dotenv import load_dotenv
from pymongo import MongoClient
import numpy as np
import asyncio

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
client = MongoClient(os.getenv('MONGODB_URL'))
db = client['jbucks']

bot = commands.Bot('j!', commands.DefaultHelpCommand(no_category="JBucks"))
import user
import jobs

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send('Bad arguments')
    if isinstance(error, commands.CommandInvokeError):
        await ctx.send('Bad arguments')
    if isinstance(error, commands.MissingPermissions):
        await ctx.send('You do not have permission to run this command')
    raise error

@bot.command(name='daily', help='print your daily JBuck')
async def daily(ctx):
    juser = user.JUser(ctx.author.id)
    if juser.daily_available:
        await ctx.send(juser.daily())
    else:
        await ctx.send('You are attempting to gain more than ur alloted Jbucks')
    juser.save()

@bot.command(name='pay', help='pay <amount> <@user> <reason?>')
async def pay(ctx, amount: float, target: discord.Member, *reasons):
    juser = user.JUser(ctx.author.id)
    target_user = user.JUser(target.id)
    reason = ' '.join(reasons)

    if amount <= 0:
        await ctx.send('You can only send a positive amount of JBucks')
        return

    if juser.jbucks < amount:
        await ctx.send('You are too poor for this request (You have {} Jbucks)'.format(juser.jbucks))
        return

    juser.add_jbucks(round(-1. * amount, 2))
    target_user.add_jbucks(amount)
    db.transactions.insert_one({
        'ts': datetime.now(),
        'from': juser.user_id,
        'to': target_user.user_id,
        'amount': amount,
        'reason': reason,
    })
    juser.save()
    target_user.save()
    await ctx.send('You have paid {} Jbucks to {}#{}. You now have {} Jbucks and they have {}.'
                   .format(amount, target.name, target.discriminator, round(juser.jbucks, 2), round(target_user.jbucks, 2)))

@bot.command(name='viewjobs', brief='viewjobs <type?>',
    help='"posted" to see only your jobs; "accepted" to see accepted by you; "all" to see all, including accepted')
async def viewjobs(ctx, mine=None):
    await view(ctx, 'jobs', mine)

@bot.command(name='viewservices', brief='viewservices <type?>',
    help='"posted" to see only your services; "accepted" to see accepted by you; "all" to see all, including accepted')
async def viewservices(ctx, mine=None):
    await view(ctx, 'services', mine)

async def view(ctx, type, mine=None):
    fil = {}
    fil['income'] = {'$gt': 0} if type == 'jobs' else {'$lte': 0}
    if mine == 'posted':
        fil['accepted'] = 0
        fil['employer'] = ctx.author.id
    elif mine == 'accepted':
        juser = user.JUser(ctx.author.id)
        fil['accepted'] = juser.user_id
    elif mine == 'all':
        pass
    else:
        fil['accepted'] = 0

    embed = discord.Embed(title='Current {}'.format(type))
    if db.jobs.count_documents(fil) == 0:
        await ctx.send("No jobs found")
        return
    for j in db.jobs.find(fil):
        job = jobs.Job()
        job.load(j)
        embed.add_field(name=job.name, value=await get_job_output(job))
    await ctx.send(embed=embed)

async def get_job_output(job):
    employer = await bot.fetch_user(job.employer)
    if not employer:
        return "Employer no longer available"

    income_str = ""
    if job.income > 0:
        income_str = 'Income: {}'.format(job.income)
    else:
        income_str = 'Cost: {}'.format(-1 * job.income)

    accepted_str = ""
    if job.accepted:
        accepted_by =  await bot.fetch_user(job.accepted)
        accepted_str = "\nAccepted by: {}#{}".format(accepted_by.name, accepted_by.discriminator)
    return r"""
        ID: {}
        {}
        Repeats: {}
        {}: {}
        Description: {}{}
    """.format(job._id,
               income_str,
               job.repeats,
               'Employer' if job.income > 0 else 'Seller',
               '{}#{}'.format(employer.name, employer.discriminator),
               job.description,
               accepted_str,
    )

@bot.command(name='postservice', usage='<cost> <never|daily> <name>:<description>',
    brief='postservice <cost> <never|daily> <name>:<description>',
    help='If "never" is set, there is a one-time transfer when the job is accepted.')
async def postservice(ctx, income: float, repeats, *args):
    await postjob(ctx, -1 * income, repeats, *args)

@bot.command(name='postjob', usage='<income> <never|daily> <name>:<description>',
    brief='postjob <income> <never|daily> <name>:<description>',
    help='If "never" is set, there is a one-time transfer when the job is accepted.')
async def postjob(ctx, income: float, repeats, *args):
    if repeats not in ['never', 'daily']:
        await ctx.send("Please specify if the job pays once or daily")
        return
    [name, description] = (' '.join(args)).split(':')
    new_job = jobs.Job(db.globals.find_one_and_update({'key': 'job_counter'}, { '$inc': {'value': 1}}).get('value'))
    new_job.income = income
    new_job.repeats = repeats
    new_job.name = name
    new_job.description = description
    new_job.employer = ctx.author.id
    new_job.save()

    embed = discord.Embed()
    embed.add_field(name=name, value=await get_job_output(new_job))
    await ctx.send('Successfully Added Job', embed=embed)

@bot.command(name='delete', aliases=['deleteservice', 'deletejob'], help='deletejob <job_id>')
async def deletejob(ctx, job_id: int):
    job = db.jobs.find_one({'_id': job_id})
    if not job:
        await ctx.send("Could not find job")
        return

    if job.get('employer') != ctx.author.id:
        await ctx.send("This is not your job")
        return

    if db.jobs.delete_one({'_id': job_id}).deleted_count:
        await ctx.send("Successfully Deleted Job {}".format(job_id))

@bot.command(name='accept', aliases=['acceptjob', 'acceptservice'], help='accept <job_id>')
async def accept(ctx, job_id: int):
    job_doc = db.jobs.find_one({'_id': job_id})
    if not job_doc:
        await ctx.send("Could not find job")
        return

    juser = user.JUser(ctx.author.id)
    juser.save()

    job = jobs.Job()
    job.load(job_doc)

    if job.accepted:
        await ctx.send("Job is already taken")
        return

    employer = await bot.fetch_user(job.employer)
    jemployer = user.JUser(employer.id)
    embed = discord.Embed()
    embed.add_field(name=job.name, value=await get_job_output(job))
    if (job.income <= 0 and juser.jbucks < -1 * job.income):
        await ctx.send('Sorry, you do not have enough jbux for this service (You have {} jbux)'.format(juser.jbucks))
        return
    if (job.income > 0 and jemployer.jbucks < job.income):
        await ctx.send('Sorry, your employer does not have enough jbux to hire you (They have {} jbux)'.format(jemployer.jbucks))
        return

    await ctx.send('Hey {}, {} has accepted your job:'.format(employer.mention if employer else job.employer, ctx.author.mention), embed=embed)

    if job.repeats == 'never':
        await transfer(ctx, user.JUser(job.employer), employer.mention, juser, ctx.author.mention, job.income, job.name)
    else:
        db.jobs.update_one({'_id': job_id}, {'$set': {'accepted': ctx.author.id}})

@bot.command(name='quit', aliases=['quitjob'], help='quit <job_id>')
async def quitjob(ctx, job_id: int):
    juser = user.JUser(ctx.author.id)
    job_doc = db.jobs.find_one({'_id': job_id})

    if not job_doc:
        await ctx.send("Could not find job")
        return

    job = jobs.Job()
    job.load(job_doc)

    if job.accepted != ctx.author.id:
        await ctx.send("This is not your job")
        return

    juser.save()
    db.jobs.update_one({'_id': job_id}, { '$set': {'accepted': 0}})

    embed = discord.Embed()
    job.accepted = 0
    embed.add_field(name=job.name, value=await get_job_output(job))
    await ctx.send('You have quit your job:', embed=embed)

async def transfer(ctx, source, source_mention, to, to_mention, amount, reason=''):
    if amount > 0:
        source.jbucks -= amount
        to.jbucks += round(.9 * amount, 2)
        add_prize_pool(round(.1 * amount, 2))
        await ctx.send('{} has transferred {} JBucks to {}.\n{} of that amount has been taxed and added to the Jelly Prize Pool (JPP)'.format(
            source_mention,
            amount,
            to_mention,
            round(.1 * amount, 2),
        ))
        db.transactions.insert_one({
            'ts': datetime.now(),
            'from': source.user_id,
            'to': to.user_id,
            'amount': amount,
            'reason': reason,
        })
        source.add_tickets(amount)
    else:
        amount = -1 * amount
        source.jbucks += round(.9 * amount, 2)
        to.jbucks -= amount
        add_prize_pool(round(.1 * amount, 2))
        await ctx.send('{} has transferred {} JBucks to {}.\n{} of that amount has been taxed and added to the Jelly Prize Pool (JPP)'.format(
            to_mention,
            amount,
            source_mention,
            round(.1 * amount, 2),
        ))
        db.transactions.insert_one({
            'ts': datetime.now(),
            'from': to.user_id,
            'to': source.user_id,
            'amount': -1 * amount,
            'reason': reason,
        })
        to.add_tickets(amount)


    source.save()
    to.save()

@bot.command(name='raffle', help='start a raffle (admin only)')
@commands.has_permissions(administrator=True)
async def raffle(ctx):
    await ctx.send("Starting raffle with a prizepool of {} Jbux...".format(round(get_prize_pool(), 2)))
    user_list = []
    ticket_list = []
    for usr in db.user.find({'$gt': { 'raffle_tickets': 0 }}):
        user_list.append(await bot.fetch_user(usr.get('user_id')))
        ticket_list.append(int(100 * usr.get('raffle_tickets')))
    ticket_list = np.array(ticket_list)
    ticket_list = np.divide(ticket_list, ticket_list.sum())
    await asyncio.sleep(2)

    [first, second, third] = np.random.default_rng().choice(user_list, 3, False, ticket_list)

    await ctx.send('Third place is...')
    await asyncio.sleep(2)
    await ctx.send('{}! You have been awarded half (.5) of a Jbuck'.format(third.mention))
    third_juser = user.JUser(third.id)
    third_juser.jbucks += .5
    third_juser.save()
    await asyncio.sleep(2)

    await ctx.send('Second place is...')
    await asyncio.sleep(2)
    await ctx.send('{}! You have been awarded one (1) Jbuck'.format(second.mention))
    second_juser = user.JUser(second.id)
    second_juser.jbucks += 1
    second_juser.save()
    await asyncio.sleep(2)

    jpp = round(get_prize_pool(), 2)
    await ctx.send('First place is...')
    await asyncio.sleep(2)
    await ctx.send('{}! You have been awarded {} Jbucks!'.format(first.mention, jpp))
    first_juser = user.JUser(first.id)
    first_juser.jbucks += jpp
    first_juser.save()

    db.globals.update_one({'key': 'prize_pool'}, { '$set': {'value': 0}})
    db.user.update_many({}, { '$set': {'raffle_tickets': 0}})


@bot.command(name='transactions', help='check your transaction history. j!transactions all for all transactions')
async def transactions(ctx, fil=None):
    filter_dict = {}
    if fil == 'all':
        pass
    else:
        filter_dict['$or'] = [
            {'to': ctx.author.id},
            {'from': ctx.author.id},
        ]

    embed = discord.Embed(title="Transaction History")
    for entry in db.transactions.find(filter_dict).sort('ts', -1):
        to_user = await bot.fetch_user(entry.get('to'))
        from_user = await bot.fetch_user(entry.get('from'))
        embed.add_field(name='{}: {}'.format(entry.get('ts'), entry.get('reason')),
                        value='{}#{} paid {}#{} {} Jbux'.format(from_user.name, from_user.discriminator, to_user.name,
                                                                to_user.discriminator, entry.get('amount')), inline=False)
    await ctx.send(embed=embed)

@bot.command(name='bal', brief='bal <user?>',
    help='check your jbucks balance, or that of a mentioned user')
async def bal(ctx, usr : discord.Member = None):
    if usr:
        juser = user.JUser(usr.id)
        await ctx.send('{}#{}\'s current balance is {} Jbucks'.format(usr.name, usr.discriminator, round(juser.jbucks, 2)))
    else:
        juser = user.JUser(ctx.author.id)
        await ctx.send('Your current balance is {} Jbucks'.format(round(juser.jbucks, 2)))

@bot.command(name='tickets', brief='tickets <user?>',
    help='check your ticket count, or that of a mentioned user')
async def tickets(ctx, usr : discord.Member = None):
    if usr:
        juser = user.JUser(usr.id)
        await ctx.send('{}#{} has {} raffle tickets'.format(usr.name, usr.discriminator, round(juser.raffle_tickets, 2)))
    else:
        juser = user.JUser(ctx.author.id)
        await ctx.send('You have {} raffle tickets'.format(round(juser.raffle_tickets, 2)))

@bot.command(name='prizepool', aliases=['jpp'], help='check prizepool')
async def prizepool(ctx):
    await ctx.send('The current prize pool is {} Jbucks'.format(round(get_prize_pool(), 2)))

@bot.command(name='gift', brief='gift <user> <amt> (admin only)', help='gifts Jbucks to target user (out of thin air) (admin only)')
@commands.has_permissions(administrator=True)
async def gift(ctx, usr: discord.Member, amt: float):
    juser = user.JUser(usr.id)
    juser.jbucks += amt
    juser.save()
    await ctx.send('{} Jbucks have been generously gifted to {}#{} by the Jelly gods'.format(amt, usr.name, usr.discriminator))

@bot.command(name='award', brief='award <user> (admin only)', help='awards all JBucks in prize pool to target user (admin only)')
@commands.has_permissions(administrator=True)
async def award(ctx, usr: discord.Member):
    amt = db.globals.find_one({'key': 'prize_pool'}).get('value', 0)
    if amt > 0:
        juser = user.JUser(usr.id)
        juser.jbucks += amt
        juser.save()

        db.globals.update_one({'key': 'prize_pool'}, { '$set': {'value': 0}})

        await ctx.send('{} Jbucks have been awarded to {}#{} from the prize pool, which is now empty'.format(amt, usr.name, usr.discriminator))

@bot.command(name='loss', brief='we lost colo, give pity jbuck (admin only)')
@commands.has_permissions(administrator=True)
async def loss(ctx):
    db.user.update_many({}, { '$inc': {'jbucks': 1}})
    await ctx.send('you suck but nice try. here\'s a jbuck <:fuck:735993594825146448>')

@bot.command(name='victory', brief='we won colo, so everyon get jbuck (admin only)')
@commands.has_permissions(administrator=True)
async def victory(ctx):
    db.user.update_many({}, { '$inc': {'jbucks': 5}})
    await ctx.send('We won colo! <:mikudab:728469356605866016> Everyone gets five (5) JBux')

@bot.command(name='leaderboard', help='check jbucks leaderboard')
async def leaderboard(ctx):
    embed = discord.Embed(title="The Official Jelly JBucks Leaderboard")
    for entry in db.user.find({}).sort('jbucks', -1):
        usr = await bot.fetch_user(entry.get('user_id'))
        embed.add_field(name='{}#{}'.format(usr.name, usr.discriminator), value=round(entry.get('jbucks'), 2), inline=False)
    await ctx.send(embed=embed)

def add_prize_pool(amount):
    db.globals.update_one({'key': 'prize_pool'}, { '$inc': {'value': round(amount, 2)}})

def get_prize_pool():
    return db.globals.find_one({'key': 'prize_pool'}).get('value', 0)

if __name__ == '__main__':
    bot.run(TOKEN)
